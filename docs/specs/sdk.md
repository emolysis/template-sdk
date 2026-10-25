# Spec: library API and CLI

Status: implemented in 0.1.0. The format itself is specified in `docs/format.md`; this
document specifies the Python API and the `emo-template` command line that implement it.
Before 1.0 the API may change in any minor release; every change is recorded in
`log/devlog.md` and here.

## Package

- Distribution `emolysis-template-sdk`, import `emolysis_template_sdk`, Python >= 3.12.
- Runtime dependencies: `pyyaml`, `jsonschema`, `sqlglot`, `duckdb`.
- Typed (`py.typed`), mypy strict clean.
- Ships `schemas/template.v0.schema.json` and `schemas/profile_constraints.v0.schema.json`
  as package data.
- Public names are exactly `emolysis_template_sdk.__all__`.
- Importing the package loads none of its modules: each public name is imported on its
  first use. `write_identifier` and `write_table` load neither DuckDB nor the runner, so a
  caller that only writes names (a SQL transpiler) does not pay for templates.

## Data types

`Problem` (frozen dataclass): `code: str`, `message: str`, `path: str` (relative to the
template directory, POSIX, empty for the directory itself), `line: int | None`,
`severity: "error" | "warning"`. `str(problem)` is `<path>[:<line>]: <severity>[<code>]
<message>`; `to_dict()` gives a JSON-ready dict. Codes are listed in `docs/format.md`
section 9 and are stable within a format version.

`Slot` (frozen dataclass): `name`, `type`, `required`, `description`, `default`,
`has_default`, `enum`.

`Template` (frozen dataclass): `path`, `id`, `shape`, `platform`, `version`, `title`,
`description`, `entry`, `slots: tuple[Slot, ...]`, `source` (entry text before
substitution), `constraints: ProfileConstraints`, `format`; properties `language`
(`sql` | `python`) and `dialect` (SQLGlot dialect); `slot(name)`.

`ProfileConstraints`: `platform`, `profile_version`, `requires`, `forbids`.

`CaseResult`: `name`, `status` (`passed` | `failed` | `skipped`), `runs_total`,
`runs_passed`, `problems`.

`RunReport`: `path`, `template_id` (None when validation failed), `problems` (validation
problems), `cases`; `ok` is true when the template is valid and no case failed;
`count(status)`; `to_dict()`.

`TemplateError(Exception)` carries `problems: list[Problem]`. `RenderError` subclasses it.

## Functions

`validate(path) -> list[Problem]`
: Checks a template directory against format v0 (manifest, entry, cost notes,
  constraints, tests tree). Never raises: a missing directory, unreadable or malformed
  files and unexpected values are all problems; an unexpected exception inside the
  validator becomes one `internal` problem. Does not execute SQL or Python; it compiles
  rendered Python and parses rendered SQL with SQLGlot (stand-in slot values) to report
  `entry-python-invalid` and the `entry-sql-unparsable` warning. An empty list means
  valid. Problems come in check order: manifest, entry, `cost.md`,
  `profile_constraints.json`, tests.

`load_template(path) -> Template`
: Runs the same checks except the tests tree and raises `TemplateError` with the error
  problems if any. Warnings do not block loading.

`render(template, slot_values=None) -> str`
: Resolves each declared slot to the given value or its default, checks the value against
  the slot type, and substitutes every `{{ slot }}`. Raises `RenderError` listing every
  `slot-unknown`, `slot-missing` and `slot-value-invalid` problem at once. Rendering rules
  per slot type and language are in `docs/format.md` section 4.

`run_tests(path) -> RunReport`
: Validates first; with any validation error it returns a report with no cases. Otherwise
  runs every case (sorted by name) with the semantics in `docs/format.md` section 8 and
  returns the report. Does not raise for problems in the template or its tests. Executes
  the template's SQL (in DuckDB) and Python (in this process) with the caller's
  privileges; it does not sandbox them.

`transpile_to_duckdb(sql, dialect, path="") -> list[str] | Problem`
: SQLGlot transpilation used by the runner, one DuckDB statement per input statement, or
  a `transpile-failed` problem.

`new_template(shape, platform, directory) -> Path`
: Writes a valid skeleton: two `table` slots, an entry that copies the source into the
  target, cost notes, constraints and one passing case `tests/basic`. Raises `ValueError`
  for an unknown shape or platform and `FileExistsError` when the directory exists and is
  not empty.

`manifest_schema()`, `constraints_schema()`
: Copies of the shipped JSON Schemas.

`write_identifier(name, dialect) -> str`
: One identifier as a slot value renders in `dialect` (`docs/format.md` section 4): quoted
  when the dialect reserves it, in the case the dialect holds an unquoted name (Snowflake
  `"ORDER"`, DuckDB `"order"`), else as given. `name` matches `[A-Za-z_][A-Za-z0-9_]*`.

`write_table(name, dialect) -> str`
: A table name of one to three parts, each written as `write_identifier` writes it.

Constants: `FORMAT_V0`, `SHAPES` (id -> display name), `PLATFORMS` (id -> display name,
including `duckdb`), `DIALECTS` (platform -> SQLGlot dialect), `SLOT_TYPES`.

## CLI: `emo-template`

Installed as a console script; `python -m emolysis_template_sdk` is equivalent.

| Command | Does | Exit |
| --- | --- | --- |
| `validate DIR... [--json]` | validates each directory, prints problems | 0 no errors (warnings allowed), 1 any error |
| `test DIR... [--json]` | `run_tests` on each directory; executes the templates, and `test --help` says so | 0 every template valid and no case failed, 1 otherwise |
| `new SHAPE PLATFORM DIR` | `new_template` | 0 created, 1 directory not empty or not writable |
| `--version`, `--help` | | 0 |

Exit code 2 is a usage error: unknown command, missing argument, unknown shape or
platform for `new`.

Text output of `validate`: one line per directory, `<dir>: ok`,
`<dir>: ok, N warnings` or `<dir>: N errors[, M warnings]`, followed by one indented line
per problem; with more than one directory a summary line
`N templates checked, M with errors`.

Text output of `test`: per directory a header `<dir> (<template id>)`, then per case
`pass|FAIL|skip  <case>  (<passed>/<total> runs)` with its problems indented; a template
with validation errors prints its problems and `not run: the template has validation
errors`. Last line: `N passed, M failed, K skipped[, T templates not run]`.

JSON output (`--json`): `{"templates": [...]}` where each item is, for `validate`,
`{"path", "ok", "problems": [Problem.to_dict()]}` and, for `test`, `RunReport.to_dict()`.
