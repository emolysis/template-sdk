# Development

## Toolchain

- Python 3.12 or newer (CI uses 3.12).
- [uv](https://docs.astral.sh/uv/) for environments, locking and building.
- [Task](https://taskfile.dev) 3 (`uv tool install go-task-bin` puts `task` in
  `~/.local/bin`).

```sh
task setup     # uv sync --locked: .venv with the package (editable) and dev tools
task gate      # what CI runs; must pass before a change is done
task --list    # every task with a description
```

`task setup` is idempotent and never changes `uv.lock`. To change dependencies, edit
`pyproject.toml`, run `uv lock`, commit both files.

## The gate

`task gate` runs, in order, and never writes to the tree:

1. `lint`: `ruff format --check .` and `ruff check .` (line length 100).
2. `typecheck`: mypy strict on `src/`, `scripts/` and `tests/`.
3. `test`: pytest, including hypothesis fuzz tests (`tests/test_fuzz.py`).
4. `fixtures:check`: every Parquet file under `examples/` and `tests/fixtures/` matches its
   definition in `scripts/make_fixtures.py`, and nothing else is there.
5. `reserved:check`: `src/emolysis_template_sdk/reserved_duckdb.py` holds the reserved
   keywords of the installed DuckDB, from that version (`scripts/make_reserved_words.py`).
6. `examples`: `emo-template validate` and `emo-template test` on every example.
7. `package`: builds the wheel into a temp directory and checks it contains the JSON
   Schemas and `py.typed`.

`task fmt` fixes formatting and auto-fixable lint in place. Template entry files under
`examples/` and `tests/fixtures/` are excluded from ruff and mypy: they contain
`{{ slot }}` references and are not Python until rendered.

## Running things

```sh
uv run emo-template validate examples/aggregation-gold-duckdb
uv run emo-template test --json tests/fixtures/valid/databricks-sql
task test -- -k runner -x          # pass pytest arguments after --
task test -- tests/test_fuzz.py --hypothesis-seed=1
```

## Fixtures

Two kinds of test data live in the repository:

- `examples/<name>/`: complete example templates. They must validate and pass.
- `tests/fixtures/valid/`: small valid templates covering each platform, Python entries
  and multi-run state.
- `tests/fixtures/invalid/<code>/`: one directory per validator problem code. Each is a
  copy of `valid/minimal` with exactly one defect, and the validator must report exactly
  `<code>` for it.
- `tests/fixtures/failing/<name>/`: valid templates whose tests fail in the runner;
  `tests/test_runner.py` maps each name to the expected problem code.

Parquet files are never edited by hand. `scripts/make_fixtures.py` defines each table as a
DuckDB query; `task fixtures` writes them and `task fixtures:check` (part of the gate)
compares the committed files with the definitions. Every Parquet file under
`tests/fixtures/invalid/` and `tests/fixtures/failing/` holds the same generic two-row
table unless the script says otherwise.

DuckDB's reserved keywords are generated the same way: `task reserved` writes
`reserved_duckdb.py` from `duckdb_keywords()` of the installed DuckDB, and
`task reserved:check` (part of the gate) fails when a DuckDB upgrade changed them. The
Snowflake list in `reserved.py` is copied by hand from the page it names, with the date it
was read. `tests/fixtures/renders/` holds each example's and valid fixture's render, per
test case, from before reserved words were quoted; `tests/test_reserved.py` checks they
still render byte for byte the same.

### Adding a validator check

1. Add the code, severity and meaning to the table in `docs/format.md` section 9, and the
   rule to the section it belongs to. Add a changelog row if the format changes.
2. Implement the check in `validate.py` without cascading into other codes.
3. Copy `tests/fixtures/valid/minimal` to `tests/fixtures/invalid/<code>/` and introduce
   exactly one defect. `test_each_invalid_fixture_reports_exactly_its_code` and
   `test_problem_codes_are_documented_and_covered` pick it up.
4. If the fixture needs different Parquet data, add it to `TABLES` in
   `scripts/make_fixtures.py` and run `task fixtures`.

### Adding a runner check

Add the code to `docs/format.md` with stage `test`, implement it in `runner.py`, add a
directory under `tests/fixtures/failing/` (and its expected code in `FAILING_CODES` in
`tests/test_runner.py`) or a focused test, and add the code to the runner set in
`test_problem_codes_are_documented_and_covered`.

### Changing the format

Read the versioning policy in `docs/format.md` section 10 first. Update the spec, the
schemas, `spec.py`, the validator, the scaffold, the example, fixtures and tests in one
change, and add a changelog row.

## Releasing

Not set up yet; nothing is published to PyPI. Planned: tag `vX.Y.Z` on `main`, build with
`uv build`, publish from a GitHub Actions workflow with trusted publishing. Until then,
install from the repository URL.

## Troubleshooting

- `uv sync --locked` fails: `pyproject.toml` changed without `uv lock`. Run `uv lock` and
  commit `uv.lock`.
- A transpiled test fails after a SQLGlot upgrade: compare
  `transpile_to_duckdb(...)` output before and after; the change may be a SQLGlot fix or
  regression. Pin and report rather than loosening the comparison.
- `fixtures:check` reports a file "not defined": a Parquet file was added outside the
  script. Define it in `scripts/make_fixtures.py` or delete it.
