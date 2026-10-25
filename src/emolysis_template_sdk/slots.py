"""Slots: declarations, value checks, placeholder scanning and substitution.

Implements docs/format.md sections 4 ("Slots") and 5 ("Entry file and substitution"),
which are normative; where this module disagrees with them, this module is wrong.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp
from sqlglot.errors import ErrorLevel, SqlglotError

from .reserved import write_identifier, write_table
from .spec import DURATION_RE, DURATION_UNITS, IDENTIFIER_RE, TABLE_RE


@dataclass(frozen=True, slots=True)
class Slot:
    """One declared slot of a template."""

    name: str
    type: str
    required: bool = False
    description: str = ""
    default: object = None
    has_default: bool = False
    enum: tuple[str, ...] = ()


# --- placeholders -----------------------------------------------------------------------

PLACEHOLDER_RE = re.compile(r"\{\{[ \t]*([A-Za-z_][A-Za-z0-9_]*)[ \t]*\}\}")
_OPENER_RE = re.compile(r"\{\{|\{%|\{#")


@dataclass(frozen=True, slots=True)
class PlaceholderScan:
    """Result of scanning an entry file for `{{ slot }}` references."""

    used: dict[str, int] = field(default_factory=dict)
    """Slot name -> line of its first reference (1-based)."""
    invalid: list[tuple[int, str]] = field(default_factory=list)
    """(line, snippet) for every `{{`, `{%` or `{#` that is not a valid placeholder."""


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def scan_placeholders(source: str) -> PlaceholderScan:
    """Find slot references and anything that looks like other template syntax."""
    scan = PlaceholderScan()
    pos = 0
    while True:
        opener = _OPENER_RE.search(source, pos)
        if opener is None:
            return scan
        start = opener.start()
        valid = PLACEHOLDER_RE.match(source, start) if opener.group() == "{{" else None
        if valid is not None:
            scan.used.setdefault(valid.group(1), _line_of(source, start))
            pos = valid.end()
            continue
        line_end = source.find("\n", start)
        snippet = source[start : line_end if line_end != -1 else len(source)][:40]
        scan.invalid.append((_line_of(source, start), snippet))
        pos = start + 2


def substitute(source: str, rendered: Mapping[str, str]) -> str:
    """Replace every `{{ name }}` with `rendered[name]`. All names must be present."""
    return PLACEHOLDER_RE.sub(lambda match: rendered[match.group(1)], source)


# --- value checks ----------------------------------------------------------------------


def _short(value: object, limit: int = 60) -> str:
    try:
        text = repr(value)
    except Exception:  # repr of arbitrary objects can fail
        text = f"<{type(value).__name__}>"
    return text if len(text) <= limit else text[: limit - 3] + "..."


@contextmanager
def quiet_sqlglot() -> Iterator[None]:
    """Silence SQLGlot's 'falling back to a Command' warnings while we probe SQL."""
    logger = logging.getLogger("sqlglot")
    previous = logger.level
    logger.setLevel(logging.ERROR)
    try:
        yield
    finally:
        logger.setLevel(previous)


def _first_line(exc: BaseException) -> str:
    text = str(exc).strip().splitlines()
    return text[0] if text else type(exc).__name__


def check_expression(text: str, dialect: str) -> str | None:
    """Return why `text` is not a single SQL expression in `dialect`, or None if it is."""
    if not text.strip():
        return "expected a SQL expression, got an empty string"
    if ";" in text:
        return "a SQL expression must not contain ';'"
    try:
        with quiet_sqlglot():
            statements = sqlglot.parse(f"SELECT (\n{text}\n)", read=dialect)
    except SqlglotError as exc:
        return f"not a valid SQL expression in dialect {dialect}: {_first_line(exc)}"
    except Exception as exc:  # SQLGlot can raise plain errors on odd input
        return f"not a valid SQL expression in dialect {dialect}: {_first_line(exc)}"
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        return "expected one SQL expression, not a statement"
    select = statements[0]
    extra = [k for k, v in select.args.items() if k != "expressions" and v not in (None, [], False)]
    if extra or len(select.expressions) != 1:
        return "expected one SQL expression, not a statement or a list"
    inner = select.expressions[0].this
    if isinstance(inner, exp.Query) and not isinstance(inner, exp.Subquery):
        return "a bare query is not an expression; put a scalar subquery in parentheses"
    if isinstance(inner, exp.Alias):
        return "an expression must not carry an alias; alias it in the entry file"
    return None


def _parse_select_item(text: str, dialect: str) -> exp.Expression | str:
    """Parse one select-list item (an expression with an optional alias).

    Returns the parsed node, or a string saying why `text` is not one item.
    """
    if not text.strip():
        return "expected a SQL expression, got an empty string"
    if ";" in text:
        return "a SQL expression must not contain ';'"
    try:
        with quiet_sqlglot():
            statements = sqlglot.parse(f"SELECT\n{text}\n", read=dialect)
    except SqlglotError as exc:
        return f"not a valid SQL expression in dialect {dialect}: {_first_line(exc)}"
    except Exception as exc:  # SQLGlot can raise plain errors on odd input
        return f"not a valid SQL expression in dialect {dialect}: {_first_line(exc)}"
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        return "expected one SQL expression with an optional alias, not a statement"
    select = statements[0]
    extra = [k for k, v in select.args.items() if k != "expressions" and v not in (None, [], False)]
    if extra or len(select.expressions) != 1:
        return "expected one SQL expression with an optional alias, not a list or a clause"
    item: exp.Expression = select.expressions[0]
    inner = item.this if isinstance(item, exp.Alias) else item
    if isinstance(inner, exp.Query) and not isinstance(inner, exp.Subquery):
        return "a bare query is not an expression; put a scalar subquery in parentheses"
    return item


def _generate_select_item(item: exp.Expression, dialect: str) -> str:
    return item.sql(dialect=dialect, comments=False, unsupported_level=ErrorLevel.RAISE)


def check_select_item(text: str, dialect: str) -> str | None:
    """Return why `text` is not one SQL expression with an optional alias, or None."""
    parsed = _parse_select_item(text, dialect)
    if isinstance(parsed, str):
        return parsed
    try:
        with quiet_sqlglot():
            written = _generate_select_item(parsed, dialect)
    except SqlglotError as exc:
        return f"SQLGlot cannot write this expression in dialect {dialect}: {_first_line(exc)}"
    except Exception as exc:  # SQLGlot can raise plain errors on odd input
        return f"SQLGlot cannot write this expression in dialect {dialect}: {_first_line(exc)}"
    if isinstance(_parse_select_item(written, dialect), str):
        # The rendered item is the written form, so it must read back (`:`'`` in Spark).
        return (
            f"SQLGlot writes this expression in dialect {dialect} as {written!r}, "
            "which does not parse"
        )
    return None


def normalize_select_item(text: str, dialect: str) -> str:
    """Rewrite a select-list item the way SQLGlot writes it in `dialect`.

    Keywords and function names come out upper case, comments are dropped and an alias is
    always written with `AS`. The result is exactly one select-list item. `text` must pass
    `check_select_item`; otherwise this raises `ValueError`.
    """
    parsed = _parse_select_item(text, dialect)
    if isinstance(parsed, str):
        raise ValueError(parsed)
    with quiet_sqlglot():
        return _generate_select_item(parsed, dialect)


def parse_duration(value: str) -> tuple[int, str, int] | None:
    """Parse `<n> <unit>`; return (n, SQL interval unit, total seconds) or None."""
    match = DURATION_RE.fullmatch(value)
    if match is None:
        return None
    amount = int(match.group(1))
    unit, seconds = DURATION_UNITS[match.group(2).lower()]
    return amount, unit, amount * seconds


def check_value(slot: Slot, value: object, dialect: str) -> str | None:
    """Return why `value` is not valid for `slot`, or None when it is."""
    kind = slot.type
    if kind in ("identifier", "column"):
        if isinstance(value, str) and IDENTIFIER_RE.fullmatch(value):
            return None
        return f"expected a plain identifier ([A-Za-z_][A-Za-z0-9_]*), got {_short(value)}"
    if kind == "table":
        if isinstance(value, str) and TABLE_RE.fullmatch(value):
            return None
        return f"expected a table name like orders or schema.orders, got {_short(value)}"
    if kind == "columns":
        if not isinstance(value, list) or not value:
            return f"expected a non-empty list of column names, got {_short(value)}"
        seen: set[str] = set()
        for item in value:
            if not isinstance(item, str) or not IDENTIFIER_RE.fullmatch(item):
                return f"expected a list of plain identifiers, got item {_short(item)}"
            if item.lower() in seen:
                return f"column {item!r} is listed twice"
            seen.add(item.lower())
        return None
    if kind == "expression":
        if not isinstance(value, str):
            return f"expected a SQL expression as a string, got {_short(value)}"
        return check_expression(value, dialect)
    if kind == "expressions":
        if not isinstance(value, list) or not value:
            return f"expected a non-empty list of SQL expressions, got {_short(value)}"
        for number, item in enumerate(value, start=1):
            if not isinstance(item, str):
                return f"item {number}: expected a SQL expression as a string, got {_short(item)}"
            reason = check_select_item(item, dialect)
            if reason is not None:
                return f"item {number}: {reason}"
        return None
    if kind == "string":
        return None if isinstance(value, str) else f"expected a string, got {_short(value)}"
    if kind == "integer":
        if isinstance(value, int) and not isinstance(value, bool):
            return None
        return f"expected an integer, got {_short(value)}"
    if kind == "boolean":
        return None if isinstance(value, bool) else f"expected true or false, got {_short(value)}"
    if kind == "duration":
        if isinstance(value, str) and parse_duration(value) is not None:
            return None
        return f"expected a duration like '2 days' or '15m', got {_short(value)}"
    if kind == "enum":
        if isinstance(value, str) and value in slot.enum:
            return None
        allowed = ", ".join(slot.enum)
        return f"expected one of [{allowed}], got {_short(value)}"
    return f"unknown slot type {kind!r}"


# --- rendering -------------------------------------------------------------------------


def render_value(slot: Slot, value: object, language: str, dialect: str) -> str:
    """Render a value that passed `check_value` as entry-file text."""
    if language == "python":
        return _render_python(slot, value)
    return _render_sql(slot, value, dialect)


def _render_sql(slot: Slot, value: object, dialect: str) -> str:
    kind = slot.type
    if kind in ("identifier", "column"):
        return write_identifier(str(value), dialect)
    if kind == "table":
        return write_table(str(value), dialect)
    if kind == "columns":
        assert isinstance(value, list)
        return ", ".join(write_identifier(str(item), dialect) for item in value)
    if kind == "expressions":
        assert isinstance(value, list)
        return ", ".join(normalize_select_item(str(item), dialect) for item in value)
    if kind == "string":
        return exp.Literal.string(str(value)).sql(dialect=dialect)
    if kind == "integer":
        assert isinstance(value, int)
        return str(int(value))
    if kind == "boolean":
        return exp.Boolean(this=bool(value)).sql(dialect=dialect)
    if kind == "duration":
        parsed = parse_duration(str(value))
        assert parsed is not None
        amount, unit, _ = parsed
        interval = exp.Interval(this=exp.Literal.string(str(amount)), unit=exp.Var(this=unit))
        return interval.sql(dialect=dialect)
    # expression, enum: verbatim
    return str(value)


def _render_python(slot: Slot, value: object) -> str:
    kind = slot.type
    if kind in ("columns", "expressions"):
        assert isinstance(value, list)
        return repr([str(item) for item in value])
    if kind == "integer":
        assert isinstance(value, int)
        return str(int(value))
    if kind == "boolean":
        return "True" if value else "False"
    if kind == "duration":
        parsed = parse_duration(str(value))
        assert parsed is not None
        return str(parsed[2])
    return repr(str(value))


def sample_value(slot: Slot) -> object:
    """A valid stand-in value for `slot`, used to syntax-check entry files."""
    stand_ins: dict[str, object] = {
        "identifier": f"v_{slot.name}",
        "table": f"v_{slot.name}",
        "column": f"v_{slot.name}",
        "columns": [f"v_{slot.name}_1", f"v_{slot.name}_2"],
        "expression": "1",
        "expressions": [f"v_{slot.name}_1", f"v_{slot.name}_2"],
        "string": "x",
        "integer": 1,
        "boolean": True,
        "duration": "1 day",
        "enum": slot.enum[0] if slot.enum else "x",
    }
    return stand_ins[slot.type]


def render_with(
    source: str,
    slots: Sequence[Slot],
    values: Mapping[str, object],
    language: str,
    dialect: str,
) -> str:
    """Substitute already-checked `values` (one per slot in `slots`) into `source`."""
    rendered = {s.name: render_value(s, values[s.name], language, dialect) for s in slots}
    return substitute(source, rendered)
