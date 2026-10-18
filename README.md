# Emolysis template SDK

**An entire data team. One download.** Emolysis is the agentic lakehouse for data
engineering and analytics. Direct a team of agents from your laptop to investigate
business questions, develop dashboards, and build and test pipelines for your data
platform. Those pipelines start from templates; this SDK is their public format.

The template format, a validator and a local test runner for Emolysis pipeline
templates. A template implements one pipeline shape (SCD Type 2, CDC merge, aggregation,
...) for one platform (Databricks, Snowflake, Microsoft Fabric, or DuckDB for local-only
work) as a SQL or Python entry file with typed slots, cost notes, platform constraints and
golden tests on Parquet fixtures.

Use this SDK to write and test your own templates against format v0.

## Status

Fresh scaffold, version 0.1.0 (2026-10-12).

- Template format **v0 is a draft** and may change in incompatible ways before v1. See
  [docs/format.md](docs/format.md) for the spec and its changelog.
- Implemented: the format spec and JSON Schemas, `validate`, `render`, `run_tests`, the
  `emo-template` CLI (`validate`, `new`, `test`) and one example template.
- Not yet published to PyPI. Install from source (below).
- Local tests run on DuckDB only. Templates for Databricks, Snowflake and Fabric are
  transpiled with SQLGlot to run locally; nothing in this repository runs on those
  platforms. See [ROADMAP.md](ROADMAP.md) for known gaps.

## Install

Python 3.12 or newer and [uv](https://docs.astral.sh/uv/).

```sh
uv tool install git+https://github.com/emolysis/template-sdk   # the emo-template CLI
# or, in a project
uv add git+https://github.com/emolysis/template-sdk
```

## Quickstart

```sh
emo-template new scd2 databricks my-scd2   # valid skeleton with one passing test case
emo-template validate my-scd2              # check it against format v0
emo-template test my-scd2                  # run tests/<case>/runs on DuckDB
```

`new` takes a shape (`ingest-batch`, `incremental-append`, `cdc-merge`, `scd2`,
`snapshot`, `backfill`, `late-arriving`, `dedupe-conform`, `aggregation-gold`,
`reverse-etl`) and a platform (`databricks`, `snowflake`, `fabric`, `duckdb`).

`validate` and `test` accept several directories and a `--json` flag. Exit codes: `0`
success, `1` problems found or tests failed, `2` usage error.

`emo-template test` executes the template's SQL and Python on your machine with your
privileges (DuckDB can read and write local files and load extensions); run it only on
templates you trust. `validate` never executes them.

A complete example lives in
[examples/aggregation-gold-duckdb](examples/aggregation-gold-duckdb): a gold aggregate with
`group_by` columns and `measures` expressions, and two test cases, one of them over two
runs.

```sh
emo-template test examples/aggregation-gold-duckdb
```

## What a template looks like

```
my-template/
  template.yaml              manifest: id, shape, platform, version, entry, slots
  template.sql               entry file with {{ slot }} references (or template.py)
  cost.md                    what it costs to run on the platform
  profile_constraints.json   what it needs from the platform
  tests/<case>/slots.yaml    slot values for one case
  tests/<case>/runs/01/input/<table>.parquet
  tests/<case>/runs/01/expected/<table>.parquet
```

Read [docs/writing-templates.md](docs/writing-templates.md) for a walk-through and
[docs/format.md](docs/format.md) for the rules.

## Library

```python
from emolysis_template_sdk import load_template, render, run_tests, validate

problems = validate("my-scd2")  # list[Problem]; never raises
template = load_template("my-scd2")  # raises TemplateError if invalid
sql = render(template, {"source_table": "raw.orders", "target_table": "silver.orders"})
report = run_tests("my-scd2")  # RunReport with one CaseResult per test case
assert report.ok
```

The API and CLI contract is in [docs/specs/sdk.md](docs/specs/sdk.md).

## Development

Needs uv and [Task](https://taskfile.dev) 3.

```sh
task setup   # uv sync --locked
task gate    # lint, typecheck, tests, fixture check, examples, package check
```

| Path                         | What                                                 |
| ---------------------------- | ---------------------------------------------------- |
| `src/emolysis_template_sdk/` | the package; JSON Schemas in `schemas/`              |
| `examples/`                  | example templates, tested in the gate                |
| `scripts/make_fixtures.py`   | defines and writes every Parquet fixture             |
| `tests/`                     | pytest suite; `tests/fixtures/` holds test templates |
| `docs/`                      | format spec, guides, architecture, development       |

See [docs/development.md](docs/development.md) and
[docs/contributing.md](docs/contributing.md).

## License

MIT, see [LICENSE](LICENSE). The license does not cover the Emolysis name or logo; see
[NOTICE](NOTICE).
