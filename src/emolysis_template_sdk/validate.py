"""Template validation: `validate` (never raises) and `load_template` (raises TemplateError).

Checks run in a fixed order: manifest, entry file, cost.md, profile_constraints.json,
then the tests tree. Later checks still run when earlier ones fail, as long as they do
not depend on the broken part, so one run reports as much as it can without cascades.
"""

from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass, field
from functools import cache
from importlib import resources
from pathlib import Path
from typing import Any

import jsonschema
import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

from .problems import Problem, Severity, TemplateError, errors
from .slots import (
    Slot,
    check_value,
    quiet_sqlglot,
    render_with,
    sample_value,
    scan_placeholders,
)
from .spec import (
    CASE_NAME_RE,
    CASE_SLOTS_FILE,
    CONSTRAINTS_FILE,
    COST_FILE,
    DIALECTS,
    ENTRY_FILES,
    EXPECTED_DIR,
    FORMAT_PREFIX,
    FORMAT_V0,
    IDENTIFIER_RE,
    INPUT_DIR,
    LOCAL_PLATFORM,
    MANIFEST_FILE,
    PLATFORMS,
    RUN_NAME_RE,
    RUNS_DIR,
    SLOT_NAME_RE,
    SLOT_TYPES,
    TESTS_DIR,
)
from .template import ProfileConstraints, Template
from .yamlio import YamlError, load_yaml

PathLike = str | os.PathLike[str]

_PARQUET_MAGIC = b"PAR1"


@cache
def _schema(name: str) -> dict[str, Any]:
    text = resources.files("emolysis_template_sdk").joinpath("schemas", name).read_text("utf-8")
    schema: dict[str, Any] = json.loads(text)
    return schema


@cache
def _schema_validator(name: str) -> jsonschema.protocols.Validator:
    schema = _schema(name)
    validator_cls = jsonschema.validators.validator_for(schema)
    validator_cls.check_schema(schema)
    validator: jsonschema.protocols.Validator = validator_cls(schema)
    return validator


def manifest_schema() -> dict[str, Any]:
    """The JSON Schema for template.yaml, as shipped in the package (a copy)."""
    return copy.deepcopy(_schema("template.v0.schema.json"))


def constraints_schema() -> dict[str, Any]:
    """The JSON Schema for profile_constraints.json, as shipped in the package (a copy)."""
    return copy.deepcopy(_schema("profile_constraints.v0.schema.json"))


class _Report:
    def __init__(self) -> None:
        self.problems: list[Problem] = []

    def add(
        self,
        code: str,
        message: str,
        path: str = "",
        line: int | None = None,
        severity: Severity = "error",
    ) -> None:
        self.problems.append(Problem(code, message, path, line, severity))


@dataclass
class _Manifest:
    data: dict[str, Any]
    platform: str | None
    entry: str | None
    slots: list[Slot] = field(default_factory=list)
    """Slots that are well formed (known type, valid enum list)."""
    slot_names: set[str] = field(default_factory=set)
    """Every string slot name, including slots that are otherwise malformed."""

    @property
    def dialect(self) -> str:
        return DIALECTS.get(self.platform or LOCAL_PLATFORM, "duckdb")


@dataclass
class _Files:
    manifest: _Manifest | None = None
    stop: bool = False
    source: str | None = None
    constraints: ProfileConstraints | None = None


def _json_path(parts: list[str | int]) -> str:
    text = ""
    for part in parts:
        text += f"[{part}]" if isinstance(part, int) else (f".{part}" if text else str(part))
    return text or "(root)"


def _relpath(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _visible(directory: Path) -> list[Path]:
    """Directory entries that are not hidden, sorted by name."""
    return sorted(
        (child for child in directory.iterdir() if not child.name.startswith(".")),
        key=lambda p: p.name,
    )


# --- manifest --------------------------------------------------------------------------


def _string_keys_only(data: dict[Any, Any], where: str, report: _Report) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(key, str):
            clean[key] = value
        else:
            report.add("manifest-invalid", f"{where}: key {key!r} is not a string", MANIFEST_FILE)
    return clean


def _schema_problem_code(path: list[str | int], validator: str) -> str:
    if path == ["format"]:
        return "format-unsupported"
    if path == ["shape"] and validator == "enum":
        return "shape-unknown"
    if path == ["platform"] and validator == "enum":
        return "platform-unknown"
    if len(path) == 3 and path[0] == "slots" and path[2] == "type" and validator == "enum":
        return "slot-type-unknown"
    return "manifest-invalid"


def _check_manifest(root: Path, report: _Report) -> _Manifest | None:
    manifest_path = root / MANIFEST_FILE
    if not manifest_path.is_file():
        report.add("manifest-missing", f"{MANIFEST_FILE} not found", MANIFEST_FILE)
        return None
    try:
        text = manifest_path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        report.add("yaml-invalid", f"not valid UTF-8: {exc.reason}", MANIFEST_FILE)
        return None
    try:
        loaded = load_yaml(text)
    except YamlError as exc:
        report.add("yaml-invalid", exc.message, MANIFEST_FILE, exc.line)
        return None
    if not isinstance(loaded, dict):
        kind = "empty" if loaded is None else type(loaded).__name__
        report.add("manifest-invalid", f"expected a mapping, got {kind}", MANIFEST_FILE)
        return None

    fmt = loaded.get("format")
    if isinstance(fmt, str) and fmt != FORMAT_V0:
        if fmt.startswith(FORMAT_PREFIX):
            message = f"format {fmt!r} is not supported; this SDK reads {FORMAT_V0}"
        else:
            message = f"format must be {FORMAT_V0!r}, got {fmt!r}"
        report.add("format-unsupported", message, MANIFEST_FILE)
        return None

    data = _string_keys_only(loaded, "(root)", report)
    raw_slots = data.get("slots")
    if isinstance(raw_slots, list):
        data["slots"] = [
            _string_keys_only(item, f"slots[{i}]", report) if isinstance(item, dict) else item
            for i, item in enumerate(raw_slots)
        ]

    try:
        schema_errors = sorted(
            _schema_validator("template.v0.schema.json").iter_errors(data),
            key=lambda e: [str(p) for p in e.absolute_path],
        )
    except RecursionError:
        report.add("manifest-invalid", "manifest is nested too deeply", MANIFEST_FILE)
        return None
    for error in schema_errors:
        path = list(error.absolute_path)
        code = _schema_problem_code(path, str(error.validator))
        report.add(code, f"{_json_path(path)}: {error.message}", MANIFEST_FILE)

    shape = data.get("shape")
    platform = data.get("platform")
    platform_ok = isinstance(platform, str) and platform in PLATFORMS
    entry = data.get("entry")
    manifest = _Manifest(
        data=data,
        platform=platform if platform_ok else None,
        entry=entry if isinstance(entry, str) and entry in ENTRY_FILES else None,
    )

    template_id = data.get("id")
    if (
        isinstance(template_id, str)
        and isinstance(shape, str)
        and isinstance(platform, str)
        and template_id != f"{shape}.{platform}"
    ):
        report.add(
            "id-mismatch",
            f"id {template_id!r} must be <shape>.<platform> = {shape + '.' + platform!r}",
            MANIFEST_FILE,
        )

    if isinstance(data.get("slots"), list):
        _check_slots(data["slots"], manifest, report)
    return manifest


def _check_slots(entries: list[Any], manifest: _Manifest, report: _Report) -> None:
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not isinstance(name, str):
            continue
        where = f"slots[{index}] ({name})"
        if name in manifest.slot_names:
            report.add("slot-duplicate", f"{where}: slot {name!r} is declared twice", MANIFEST_FILE)
            continue
        manifest.slot_names.add(name)
        if not SLOT_NAME_RE.fullmatch(name):
            continue  # reported by the schema

        kind = entry.get("type")
        known_type = isinstance(kind, str) and kind in SLOT_TYPES
        enum_values = entry.get("enum")
        enum_ok = True
        if kind == "enum" and "enum" not in entry:
            report.add(
                "slot-enum-invalid",
                f"{where}: enum slots must list their values in `enum`",
                MANIFEST_FILE,
            )
            enum_ok = False
        elif known_type and kind != "enum" and "enum" in entry:
            report.add(
                "slot-enum-invalid",
                f"{where}: `enum` is only allowed on slots of type enum",
                MANIFEST_FILE,
            )
            enum_ok = False
        elif kind == "enum" and not (
            isinstance(enum_values, list)
            and enum_values
            and all(isinstance(v, str) and IDENTIFIER_RE.fullmatch(v) for v in enum_values)
        ):
            enum_ok = False  # reported by the schema

        required = entry.get("required", False)
        has_default = "default" in entry
        default_ok = True
        if required is True and has_default:
            report.add(
                "slot-default-conflict",
                f"{where}: a required slot must not declare a default",
                MANIFEST_FILE,
            )
            default_ok = False
        elif required is False and not has_default:
            report.add(
                "slot-default-missing",
                f"{where}: an optional slot needs a default (or set required: true)",
                MANIFEST_FILE,
            )
        elif not isinstance(required, bool):
            default_ok = False  # reported by the schema

        if not (known_type and enum_ok):
            continue
        assert isinstance(kind, str)
        description = entry.get("description")
        slot = Slot(
            name=name,
            type=kind,
            required=required is True,
            description=description if isinstance(description, str) else "",
            default=entry.get("default"),
            has_default=has_default,
            enum=tuple(enum_values) if kind == "enum" and isinstance(enum_values, list) else (),
        )
        if has_default and default_ok:
            reason = check_value(slot, slot.default, manifest.dialect)
            if reason is not None:
                report.add("slot-default-invalid", f"{where}: default: {reason}", MANIFEST_FILE)
                continue
        manifest.slots.append(slot)


# --- entry -----------------------------------------------------------------------------


def _check_entry(root: Path, manifest: _Manifest, report: _Report) -> str | None:
    entry = manifest.entry
    if entry is None:
        return None
    present = [name for name in ENTRY_FILES if (root / name).is_file()]
    if entry not in present:
        report.add("entry-missing", f"entry file {entry} not found", entry)
        return None
    others = [name for name in present if name != entry]
    if others:
        report.add(
            "entry-ambiguous",
            f"found {', '.join(others)} next to the entry {entry}; a template has one entry file",
            others[0],
        )
    try:
        source = (root / entry).read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        report.add("entry-unreadable", f"not valid UTF-8: {exc.reason}", entry)
        return None

    scan = scan_placeholders(source)
    for line, snippet in scan.invalid:
        report.add(
            "placeholder-invalid",
            f"{snippet!r} is not a slot reference; v0 only supports {{{{ slot_name }}}}",
            entry,
            line,
        )
    undeclared = False
    for name, line in scan.used.items():
        if name not in manifest.slot_names:
            undeclared = True
            report.add(
                "placeholder-undeclared",
                f"{{{{ {name} }}}} refers to a slot that template.yaml does not declare",
                entry,
                line,
            )
    for name in sorted(manifest.slot_names):
        if name not in scan.used and SLOT_NAME_RE.fullmatch(name):
            report.add(
                "slot-unused", f"slot {name!r} is declared but never used in {entry}", MANIFEST_FILE
            )

    by_name = {slot.name: slot for slot in manifest.slots}
    if scan.invalid or undeclared or any(name not in by_name for name in scan.used):
        return source
    used_slots = [by_name[name] for name in scan.used]
    values = {slot.name: sample_value(slot) for slot in used_slots}
    language = ENTRY_FILES[entry]
    rendered = render_with(source, used_slots, values, language, manifest.dialect)
    if language == "python":
        _check_python_syntax(rendered, entry, report)
    elif manifest.platform is not None:
        _check_sql_syntax(rendered, entry, manifest.platform, report)
    return source


def _check_python_syntax(rendered: str, entry: str, report: _Report) -> None:
    try:
        compile(rendered, entry, "exec", dont_inherit=True)
    except SyntaxError as exc:
        report.add("entry-python-invalid", exc.msg or "invalid syntax", entry, exc.lineno)
    except ValueError as exc:  # for example NUL bytes
        report.add("entry-python-invalid", str(exc), entry)


def _check_sql_syntax(rendered: str, entry: str, platform: str, report: _Report) -> None:
    dialect = DIALECTS[platform]
    try:
        with quiet_sqlglot():
            statements = sqlglot.parse(rendered, read=dialect)
    except SqlglotError as exc:
        first = str(exc).strip().splitlines()
        report.add(
            "entry-sql-unparsable",
            f"SQLGlot cannot parse the entry as {dialect}: {first[0] if first else exc}",
            entry,
            severity="warning",
        )
        return
    except Exception as exc:  # SQLGlot can raise plain errors on odd input
        report.add(
            "entry-sql-unparsable",
            f"SQLGlot cannot parse the entry as {dialect}: {type(exc).__name__}: {exc}",
            entry,
            severity="warning",
        )
        return
    if platform == LOCAL_PLATFORM:
        return
    for number, statement in enumerate((s for s in statements if s is not None), start=1):
        if isinstance(statement, exp.Command):
            report.add(
                "entry-sql-unparsable",
                f"statement {number} is not understood by SQLGlot as {dialect} "
                "and cannot be transpiled for local tests",
                entry,
                severity="warning",
            )


# --- cost.md and profile_constraints.json ---------------------------------------------


def _check_cost(root: Path, report: _Report) -> None:
    path = root / COST_FILE
    if not path.is_file():
        report.add(
            "cost-missing", f"{COST_FILE} not found; describe the cost on the platform", COST_FILE
        )
        return
    if not path.read_bytes().decode("utf-8", errors="replace").strip():
        report.add("cost-empty", f"{COST_FILE} is empty", COST_FILE)


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key {key!r}")
        result[key] = value
    return result


def _check_constraints(
    root: Path, manifest: _Manifest | None, report: _Report
) -> ProfileConstraints | None:
    path = root / CONSTRAINTS_FILE
    if not path.is_file():
        report.add("constraints-missing", f"{CONSTRAINTS_FILE} not found", CONSTRAINTS_FILE)
        return None
    try:
        data = json.loads(path.read_bytes().decode("utf-8"), object_pairs_hook=_no_duplicate_keys)
    except UnicodeDecodeError as exc:
        report.add("constraints-invalid", f"not valid UTF-8: {exc.reason}", CONSTRAINTS_FILE)
        return None
    except json.JSONDecodeError as exc:
        report.add("constraints-invalid", f"invalid JSON: {exc.msg}", CONSTRAINTS_FILE, exc.lineno)
        return None
    except (ValueError, RecursionError) as exc:
        report.add("constraints-invalid", f"invalid JSON: {exc}", CONSTRAINTS_FILE)
        return None
    if not isinstance(data, dict):
        report.add(
            "constraints-invalid",
            f"expected an object, got {type(data).__name__}",
            CONSTRAINTS_FILE,
        )
        return None
    before = len(report.problems)
    validator = _schema_validator("profile_constraints.v0.schema.json")
    for error in sorted(validator.iter_errors(data), key=lambda e: [str(p) for p in e.path]):
        report.add(
            "constraints-invalid",
            f"{_json_path(list(error.absolute_path))}: {error.message}",
            CONSTRAINTS_FILE,
        )
    if len(report.problems) > before:
        return None
    constraints = ProfileConstraints(
        platform=data["platform"],
        profile_version=data["profile_version"],
        requires=tuple(data["requires"]),
        forbids=tuple(data["forbids"]),
    )
    both = sorted(set(constraints.requires) & set(constraints.forbids))
    if both:
        report.add(
            "constraints-invalid",
            f"features both required and forbidden: {', '.join(both)}",
            CONSTRAINTS_FILE,
        )
        return None
    if manifest is not None and manifest.platform not in (None, constraints.platform):
        report.add(
            "constraints-platform-mismatch",
            f"platform {constraints.platform!r} does not match {manifest.platform!r} "
            f"in {MANIFEST_FILE}",
            CONSTRAINTS_FILE,
        )
        return None
    return constraints


# --- tests tree ------------------------------------------------------------------------


def _check_tests(root: Path, manifest: _Manifest | None, report: _Report) -> None:
    tests = root / TESTS_DIR
    if not tests.is_dir():
        report.add("tests-missing", "tests/ not found; add at least one test case", TESTS_DIR)
        return
    cases: list[Path] = []
    for child in _visible(tests):
        if child.is_dir():
            cases.append(child)
        elif child.suffix != ".md":
            report.add(
                "file-unexpected", "only case directories belong in tests/", _relpath(root, child)
            )
    if not cases:
        report.add("tests-missing", "tests/ has no test cases", TESTS_DIR)
    for case in cases:
        _check_case(root, case, manifest, report)


def _check_case(root: Path, case: Path, manifest: _Manifest | None, report: _Report) -> None:
    rel = _relpath(root, case)
    if not CASE_NAME_RE.fullmatch(case.name):
        report.add(
            "case-name-invalid",
            f"case names use lower case letters, digits, '-' and '_' (got {case.name!r})",
            rel,
        )
    for child in _visible(case):
        if child.name not in (CASE_SLOTS_FILE, RUNS_DIR) and child.suffix != ".md":
            report.add(
                "file-unexpected",
                f"a case holds {CASE_SLOTS_FILE}, {RUNS_DIR}/ and optional .md notes",
                _relpath(root, child),
            )
    _check_case_slots(root, case, manifest, report)
    _check_runs(root, case, report)


def load_case_slots(case: Path) -> dict[str, Any]:
    """Read tests/<case>/slots.yaml. Raises YamlError or ValueError when it is not valid."""
    text = (case / CASE_SLOTS_FILE).read_bytes().decode("utf-8")
    loaded = load_yaml(text)
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ValueError(f"expected a mapping of slot values, got {type(loaded).__name__}")
    return loaded


def _check_case_slots(root: Path, case: Path, manifest: _Manifest | None, report: _Report) -> None:
    path = case / CASE_SLOTS_FILE
    rel = _relpath(root, path)
    if not path.is_file():
        report.add("case-slots-missing", f"{CASE_SLOTS_FILE} not found (use {{}} for none)", rel)
        return
    try:
        values = load_case_slots(case)
    except YamlError as exc:
        report.add("yaml-invalid", exc.message, rel, exc.line)
        return
    except UnicodeDecodeError as exc:
        report.add("yaml-invalid", f"not valid UTF-8: {exc.reason}", rel)
        return
    except ValueError as exc:
        report.add("case-slots-invalid", str(exc), rel)
        return
    if manifest is None:
        return
    by_name = {slot.name: slot for slot in manifest.slots}
    for key, value in values.items():
        if not isinstance(key, str) or key not in manifest.slot_names:
            report.add("slot-unknown", f"value for undeclared slot {key!r}", rel)
            continue
        slot = by_name.get(key)
        if slot is None:
            continue  # the declaration is broken and reported already
        reason = check_value(slot, value, manifest.dialect)
        if reason is not None:
            report.add("slot-value-invalid", f"{key}: {reason}", rel)
    for slot in manifest.slots:
        if slot.required and slot.name not in values:
            report.add("slot-missing", f"required slot {slot.name!r} has no value", rel)


def _check_runs(root: Path, case: Path, report: _Report) -> None:
    runs_dir = case / RUNS_DIR
    rel = _relpath(root, runs_dir)
    if not runs_dir.is_dir():
        report.add("runs-missing", f"{RUNS_DIR}/ not found; add runs/01/input and expected", rel)
        return
    children = _visible(runs_dir)
    if not children:
        report.add("runs-missing", f"{RUNS_DIR}/ has no runs", rel)
        return
    runs: list[Path] = []
    for child in children:
        if child.is_dir() and RUN_NAME_RE.fullmatch(child.name):
            runs.append(child)
        else:
            report.add(
                "runs-malformed",
                f"{child.name!r}: runs are directories named 01, 02, ...",
                _relpath(root, child),
            )
    numbers = [int(run.name) for run in runs]
    if numbers and numbers != list(range(1, len(numbers) + 1)):
        found = ", ".join(run.name for run in runs)
        report.add(
            "runs-malformed", f"runs must be numbered from 01 without gaps; found {found}", rel
        )
    for run in runs:
        _check_run(root, run, report)


def _check_run(root: Path, run: Path, report: _Report) -> None:
    rel = _relpath(root, run)
    for child in _visible(run):
        if child.name not in (INPUT_DIR, EXPECTED_DIR):
            report.add(
                "file-unexpected",
                f"a run holds only {INPUT_DIR}/ and {EXPECTED_DIR}/",
                _relpath(root, child),
            )
    for part in (INPUT_DIR, EXPECTED_DIR):
        directory = run / part
        if not directory.is_dir():
            report.add("run-incomplete", f"{part}/ not found", f"{rel}/{part}")
            continue
        tables = _check_table_files(root, directory, report)
        if part == EXPECTED_DIR and not tables:
            report.add("run-incomplete", f"{part}/ has no tables", f"{rel}/{part}")


def _check_table_files(root: Path, directory: Path, report: _Report) -> int:
    count = 0
    seen: set[str] = set()
    for child in _visible(directory):
        rel = _relpath(root, child)
        if not child.is_file() or child.suffix != ".parquet":
            report.add("file-unexpected", "only <table>.parquet files belong here", rel)
            continue
        count += 1
        if not IDENTIFIER_RE.fullmatch(child.stem):
            report.add(
                "table-name-invalid",
                f"table name {child.stem!r} is not a plain identifier ([A-Za-z_][A-Za-z0-9_]*)",
                rel,
            )
        elif child.stem.lower() in seen:
            report.add(
                "table-name-invalid", f"table {child.stem!r} appears twice (names ignore case)", rel
            )
        seen.add(child.stem.lower())
        if not _looks_like_parquet(child):
            report.add("parquet-invalid", "not a Parquet file", rel)
    return count


def _looks_like_parquet(path: Path) -> bool:
    with path.open("rb") as handle:
        head = handle.read(4)
        handle.seek(0, os.SEEK_END)
        if handle.tell() < 12:
            return False
        handle.seek(-4, os.SEEK_END)
        tail = handle.read(4)
    return head == _PARQUET_MAGIC and tail == _PARQUET_MAGIC


# --- entry points ----------------------------------------------------------------------


def _check_files(root: Path, report: _Report) -> _Files:
    files = _Files()
    if not root.is_dir():
        what = "not a directory" if root.exists() else "not found"
        report.add("template-dir-missing", f"template directory {what}: {root}")
        files.stop = True
        return files
    manifest = _check_manifest(root, report)
    files.manifest = manifest
    if manifest is None and any(p.code == "format-unsupported" for p in report.problems):
        files.stop = True
        return files
    if manifest is not None:
        files.source = _check_entry(root, manifest, report)
    _check_cost(root, report)
    files.constraints = _check_constraints(root, manifest, report)
    return files


def validate(path: PathLike) -> list[Problem]:
    """Check a template directory against format v0 and return every problem found.

    Never raises: unreadable files, bad YAML and unexpected values all come back as
    problems. An empty list means the template is valid. Warnings do not make a
    template invalid; use `problems.errors()` to keep only errors.
    """
    report = _Report()
    try:
        root = Path(path)
        files = _check_files(root, report)
        if not files.stop:
            _check_tests(root, files.manifest, report)
    except OSError as exc:
        report.add("io-error", f"{type(exc).__name__}: {exc}")
    except Exception as exc:  # validate never raises; this is a bug in the validator
        report.add("internal", f"validator error, please report: {type(exc).__name__}: {exc}")
    return report.problems


def load_template(path: PathLike) -> Template:
    """Load a template for rendering and testing.

    Checks the manifest, entry file, cost.md and profile_constraints.json (not the tests
    tree) and raises `TemplateError` with the problems if any of them is an error.
    """
    report = _Report()
    try:
        root = Path(path)
        files = _check_files(root, report)
    except OSError as exc:
        raise TemplateError([Problem("io-error", f"{type(exc).__name__}: {exc}")]) from exc
    found = errors(report.problems)
    manifest = files.manifest
    if found or manifest is None or files.source is None or files.constraints is None:
        raise TemplateError(found or [Problem("internal", "template could not be loaded")])
    data = manifest.data
    return Template(
        path=root,
        id=data["id"],
        shape=data["shape"],
        platform=data["platform"],
        version=data["version"],
        title=data["title"],
        description=data["description"],
        entry=data["entry"],
        slots=tuple(manifest.slots),
        source=files.source,
        constraints=files.constraints,
        format=data["format"],
    )
