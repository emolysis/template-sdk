"""Local test runner: run every tests/<case> of a template on DuckDB.

For each case, in a fresh in-memory DuckDB database, runs are applied in order. A run
loads its input tables, executes the rendered entry (transpiled to DuckDB when the
template targets another platform) and compares every expected table with the table the
entry produced, ignoring row order. A failing run stops its case. A caller that wants to
stop a long run passes `stop`, which is asked before each case and each run.
"""

from __future__ import annotations

import datetime as dt
import decimal
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import duckdb
import sqlglot
from sqlglot import exp
from sqlglot.errors import ErrorLevel, SqlglotError

from .problems import Problem, TemplateError, errors
from .render import resolve_slot_values
from .reserved import quote_duckdb_reserved
from .slots import quiet_sqlglot, render_with
from .spec import (
    CASE_SLOTS_FILE,
    EXPECTED_DIR,
    INPUT_DIR,
    LOCAL_PLATFORM,
    RUN_NAME_RE,
    RUNS_DIR,
    TESTS_DIR,
)
from .template import Template
from .validate import PathLike, load_case_slots, load_template, validate

CaseStatus = Literal["passed", "failed", "skipped", "stopped"]
_SAMPLE_ROWS = 5


@dataclass(frozen=True, slots=True)
class CaseResult:
    """Outcome of one test case. `stopped`: the run was stopped before the case finished;
    `runs_passed` counts the runs that passed before it."""

    name: str
    status: CaseStatus
    runs_total: int
    runs_passed: int
    problems: tuple[Problem, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "status": self.status,
            "runs_total": self.runs_total,
            "runs_passed": self.runs_passed,
            "problems": [p.to_dict() for p in self.problems],
        }


@dataclass(frozen=True, slots=True)
class RunReport:
    """Outcome of `run_tests` for one template directory.

    `problems` holds validation problems. When any of them is an error, no case runs and
    `cases` is empty. `stopped` is true when the caller's `stop` ended the run: every case
    that did not finish has the status `stopped`, and the report is not `ok`.
    """

    path: Path
    template_id: str | None
    problems: tuple[Problem, ...]
    cases: tuple[CaseResult, ...]
    stopped: bool = False

    @property
    def ok(self) -> bool:
        """True when the template is valid, the run was not stopped and no case failed."""
        return (
            self.template_id is not None
            and not self.stopped
            and not errors(self.problems)
            and all(case.status != "failed" for case in self.cases)
        )

    def count(self, status: CaseStatus) -> int:
        return sum(1 for case in self.cases if case.status == status)

    def to_dict(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "template_id": self.template_id,
            "ok": self.ok,
            "stopped": self.stopped,
            "problems": [p.to_dict() for p in self.problems],
            "cases": [case.to_dict() for case in self.cases],
        }


def run_tests(path: PathLike, *, stop: Callable[[], bool] | None = None) -> RunReport:
    """Validate the template at `path`, then run every test case on DuckDB.

    Never raises for problems in the template or its tests; they are reported in the
    returned `RunReport`. This executes the template's SQL and Python in this process
    with the caller's privileges; run it only on templates you trust.

    `stop`, when given, is called before each case and before each run of a case; when it
    returns true, nothing more runs and the report is `stopped`, with every case that did
    not finish marked `stopped`. An exception it raises is not caught.
    """
    root = Path(path)
    problems = validate(root)
    if errors(problems):
        return RunReport(root, None, tuple(problems), ())
    try:
        template = load_template(root)
    except TemplateError as exc:
        return RunReport(root, None, tuple(problems + exc.problems), ())
    cases = sorted(
        (c for c in (root / TESTS_DIR).iterdir() if c.is_dir() and not c.name.startswith(".")),
        key=lambda c: c.name,
    )
    results: list[CaseResult] = []
    for case in cases:
        if stop is not None and stop():
            break
        results.append(_run_case(template, case, stop))
    stopped = len(results) < len(cases) or any(r.status == "stopped" for r in results)
    for case in cases[len(results) :]:
        results.append(CaseResult(case.name, "stopped", len(_runs(case)), 0))
    return RunReport(root, template.id, tuple(problems), tuple(results), stopped)


# --- one case --------------------------------------------------------------------------


def _snippet(sql: str, limit: int = 60) -> str:
    text = " ".join(sql.split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _first_line(exc: BaseException) -> str:
    lines = [line for line in str(exc).strip().splitlines() if line.strip()]
    return f"{type(exc).__name__}: {lines[0]}" if lines else type(exc).__name__


def _runs(case: Path) -> list[Path]:
    runs_dir = case / RUNS_DIR
    return sorted(
        (r for r in runs_dir.iterdir() if r.is_dir() and RUN_NAME_RE.fullmatch(r.name)),
        key=lambda r: r.name,
    )


def _run_case(template: Template, case: Path, stop: Callable[[], bool] | None = None) -> CaseResult:
    rel = f"{TESTS_DIR}/{case.name}"
    runs = _runs(case)

    def failed(problem: Problem, passed: int = 0) -> CaseResult:
        return CaseResult(case.name, "failed", len(runs), passed, (problem,))

    try:
        given = load_case_slots(case)
    except Exception as exc:  # validated already; keep the runner total anyway
        return failed(Problem("case-slots-invalid", _first_line(exc), f"{rel}/{CASE_SLOTS_FILE}"))
    values, problems = resolve_slot_values(template, given, f"{rel}/{CASE_SLOTS_FILE}")
    if problems:
        return CaseResult(case.name, "failed", len(runs), 0, tuple(problems))
    rendered = render_with(
        template.source, template.slots, values, template.language, template.dialect
    )

    if template.language == "python" and template.platform != LOCAL_PLATFORM:
        note = Problem(
            "python-entry-skipped",
            f"Python entries run locally only for platform {LOCAL_PLATFORM}; "
            f"this one targets {template.platform}",
            template.entry,
            severity="warning",
        )
        return CaseResult(case.name, "skipped", len(runs), 0, (note,))

    con = duckdb.connect(":memory:")
    try:
        step = _prepare(template, rendered, con)
        if isinstance(step, Problem):
            return failed(step)
        for done, run in enumerate(runs):
            if stop is not None and stop():
                return CaseResult(case.name, "stopped", len(runs), done)
            run_rel = f"{rel}/{RUNS_DIR}/{run.name}"
            problem = _load_inputs(con, run / INPUT_DIR, f"{run_rel}/{INPUT_DIR}")
            if problem is None:
                problem = step(con, run_rel)
            if problem is not None:
                return failed(problem, done)
            mismatches = _compare_run(con, run / EXPECTED_DIR, f"{run_rel}/{EXPECTED_DIR}")
            if mismatches:
                return CaseResult(case.name, "failed", len(runs), done, tuple(mismatches))
        return CaseResult(case.name, "passed", len(runs), len(runs))
    finally:
        con.close()


Step = Callable[[duckdb.DuckDBPyConnection, str], Problem | None]


def _prepare(template: Template, rendered: str, con: duckdb.DuckDBPyConnection) -> Step | Problem:
    """Turn the rendered entry into a callable that executes one run."""
    if template.language == "python":
        return _prepare_python(template, rendered)
    if template.dialect == "duckdb":
        try:
            statements = [s.query for s in con.extract_statements(rendered)]
        except Exception as exc:
            return Problem(
                "run-failed",
                f"DuckDB cannot parse the rendered entry: {_first_line(exc)}",
                template.entry,
            )
    else:
        transpiled = transpile_to_duckdb(rendered, template.dialect, template.entry)
        if isinstance(transpiled, Problem):
            return transpiled
        statements = transpiled

    def execute(con: duckdb.DuckDBPyConnection, run_rel: str) -> Problem | None:
        for number, statement in enumerate(statements, start=1):
            try:
                con.execute(statement)
            except Exception as exc:
                snippet = _snippet(statement, 80)
                return Problem(
                    "run-failed",
                    f"statement {number} failed: {_first_line(exc)} [{snippet}]",
                    run_rel,
                )
        return None

    return execute


def transpile_to_duckdb(sql: str, dialect: str, path: str = "") -> list[str] | Problem:
    """Transpile `sql` from `dialect` to DuckDB, one string per statement.

    An identifier DuckDB reserves (`group`, `end`, ...) is written quoted. Returns a
    `transpile-failed` problem when SQLGlot cannot parse a statement, only understands it
    as an opaque command, or cannot express it in DuckDB.
    """
    try:
        with quiet_sqlglot():
            parsed = sqlglot.parse(sql, read=dialect, error_level=ErrorLevel.RAISE)
    except SqlglotError as exc:
        return Problem(
            "transpile-failed",
            f"SQLGlot cannot parse the entry as {dialect}: {_first_line(exc)}",
            path,
        )
    statements: list[str] = []
    for number, statement in enumerate((s for s in parsed if s is not None), start=1):
        snippet = _snippet(statement.sql(dialect=dialect))
        if isinstance(statement, exp.Command):
            return Problem(
                "transpile-failed",
                f"statement {number} [{snippet}] is not understood by SQLGlot as {dialect}, "
                "so it cannot run on DuckDB",
                path,
            )
        try:
            written = quote_duckdb_reserved(statement)
            statements.append(written.sql(dialect="duckdb", unsupported_level=ErrorLevel.RAISE))
        except SqlglotError as exc:
            return Problem(
                "transpile-failed",
                f"statement {number} [{snippet}] cannot be transpiled from {dialect} to duckdb: "
                f"{_first_line(exc)}",
                path,
            )
    return statements


def _prepare_python(template: Template, rendered: str) -> Step | Problem:
    filename = str(template.path / template.entry)
    namespace: dict[str, object] = {"__name__": "emolysis_template", "__file__": filename}
    try:
        code = compile(rendered, filename, "exec", dont_inherit=True)
        exec(code, namespace)
    except (Exception, SystemExit) as exc:
        return Problem(
            "run-failed", f"loading the rendered entry failed: {_first_line(exc)}", template.entry
        )
    run = namespace.get("run")
    if not callable(run):
        return Problem(
            "python-run-missing",
            "a Python entry must define run(con) at module level",
            template.entry,
        )

    def execute(con: duckdb.DuckDBPyConnection, run_rel: str) -> Problem | None:
        try:
            run(con)
        except (Exception, SystemExit) as exc:
            return Problem("run-failed", f"run(con) raised {_first_line(exc)}", run_rel)
        return None

    return execute


# --- data in and out -------------------------------------------------------------------


def _ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _literal(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def _load_inputs(con: duckdb.DuckDBPyConnection, directory: Path, rel: str) -> Problem | None:
    for parquet in sorted(directory.glob("*.parquet")):
        try:
            con.execute(
                f"CREATE OR REPLACE TABLE {_ident(parquet.stem)} AS "
                f"SELECT * FROM read_parquet({_literal(str(parquet))})"
            )
        except Exception as exc:
            return Problem("input-unreadable", _first_line(exc), f"{rel}/{parquet.name}")
    return None


_INTEGER_TYPES = {
    "TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT",
    "UTINYINT", "USMALLINT", "UINTEGER", "UBIGINT", "UHUGEINT",
}  # fmt: skip


def type_family(duckdb_type: str) -> str:
    """Coarse family of a DuckDB type; columns compare only within one family."""
    name = duckdb_type.strip().upper()
    if name.endswith("]") or name.startswith(("STRUCT", "MAP", "UNION")):
        return "nested"
    base = re.split(r"[(\s]", name, maxsplit=1)[0]
    if base in _INTEGER_TYPES or base == "DECIMAL":
        return "exact-number"
    if base in ("FLOAT", "DOUBLE", "REAL"):
        return "approximate-number"
    if base in ("VARCHAR", "CHAR", "TEXT", "STRING"):
        return "string"
    if name in ("TIMESTAMP WITH TIME ZONE", "TIMESTAMPTZ"):
        return "timestamptz"
    if base.startswith("TIMESTAMP"):
        return "timestamp"
    if base.startswith("TIME"):
        return "time"
    return base.lower()


def _columns(con: duckdb.DuckDBPyConnection, relation: str) -> list[tuple[str, str]]:
    rows = con.execute(f"DESCRIBE SELECT * FROM {relation}").fetchall()
    return [(str(row[0]), str(row[1])) for row in rows]


def _format_value(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, str):
        return repr(value)
    if isinstance(value, decimal.Decimal | dt.date | dt.time | dt.datetime):
        return str(value)
    return repr(value)


def _format_rows(rows: list[tuple[object, ...]]) -> str:
    return "; ".join("(" + ", ".join(_format_value(v) for v in row) + ")" for row in rows)


def _compare_run(con: duckdb.DuckDBPyConnection, directory: Path, rel: str) -> list[Problem]:
    problems: list[Problem] = []
    for parquet in sorted(directory.glob("*.parquet")):
        problem = _compare_table(con, parquet.stem, parquet, f"{rel}/{parquet.name}")
        if problem is not None:
            problems.append(problem)
    return problems


def _compare_table(
    con: duckdb.DuckDBPyConnection, table: str, parquet: Path, rel: str
) -> Problem | None:
    expected_rel = f"read_parquet({_literal(str(parquet))})"
    try:
        expected_cols = _columns(con, expected_rel)
    except Exception as exc:
        return Problem("input-unreadable", _first_line(exc), rel)
    try:
        actual_cols = _columns(con, _ident(table))
    except duckdb.CatalogException:
        return Problem("table-missing", f"the run did not produce table {table!r}", rel)
    except Exception as exc:
        return Problem("table-missing", f"table {table!r} cannot be read: {_first_line(exc)}", rel)

    actual = {name.lower(): (name, kind) for name, kind in actual_cols}
    expected = {name.lower(): (name, kind) for name, kind in expected_cols}
    notes: list[str] = []
    missing = [expected[k][0] for k in expected if k not in actual]
    extra = [actual[k][0] for k in actual if k not in expected]
    if missing:
        notes.append(f"missing columns {', '.join(missing)}")
    if extra:
        notes.append(f"unexpected columns {', '.join(extra)}")
    for key, (name, kind) in expected.items():
        if key in actual and type_family(kind) != type_family(actual[key][1]):
            notes.append(f"column {name}: expected {kind}, got {actual[key][1]}")
    if notes:
        return Problem("columns-mismatch", f"table {table}: {'; '.join(notes)}", rel)

    exp_select = "SELECT " + ", ".join(_ident(expected[k][0]) for k in expected)
    act_select = "SELECT " + ", ".join(_ident(actual[k][0]) for k in expected)
    exp_query = f"{exp_select} FROM {expected_rel}"
    act_query = f"{act_select} FROM {_ident(table)}"
    try:
        missing_rows = _difference(con, exp_query, act_query)
        extra_rows = _difference(con, act_query, exp_query)
    except Exception as exc:
        return Problem("compare-failed", f"table {table}: {_first_line(exc)}", rel)
    if not missing_rows[0] and not extra_rows[0]:
        return None
    parts = [f"table {table}: {_rows(missing_rows[0])} missing, {_rows(extra_rows[0])} unexpected"]
    if missing_rows[1]:
        parts.append(f"missing: {_format_rows(missing_rows[1])}")
    if extra_rows[1]:
        parts.append(f"unexpected: {_format_rows(extra_rows[1])}")
    return Problem("rows-mismatch", "\n".join(parts), rel)


def _rows(count: int) -> str:
    return f"{count} row" if count == 1 else f"{count} rows"


def _difference(
    con: duckdb.DuckDBPyConnection, left: str, right: str
) -> tuple[int, list[tuple[object, ...]]]:
    query = f"({left}) EXCEPT ALL ({right})"
    count_row = con.execute(f"SELECT count(*) FROM ({query})").fetchone()
    count = int(count_row[0]) if count_row is not None else 0
    sample = (
        con.execute(f"SELECT * FROM ({query}) LIMIT {_SAMPLE_ROWS}").fetchall() if count else []
    )
    return count, [tuple(row) for row in sample]
