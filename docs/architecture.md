# Architecture

The SDK is a small, dependency-light Python package. It reads a template directory, checks
it against format v0, renders its entry file and runs its golden tests on DuckDB. The SDK
itself makes no network calls and has no configuration files and no global state beyond two
cached JSON Schemas. `docs/format.md` is the normative spec; this package is its reference
implementation.

Running tests is different: `run_tests` executes the template's SQL in DuckDB and its
Python in the test process, with the user's privileges. DuckDB SQL can read and write local
files and install and load extensions, which can reach the network. The SDK does not
sandbox templates; the docs tell users to test only templates they trust. `validate` never
executes a template.

## Modules

```
src/emolysis_template_sdk/
  spec.py        format vocabulary: FORMAT_V0, shapes, platforms, dialects, slot types,
                 file names, name patterns, duration units
  problems.py    Problem, errors(), TemplateError, RenderError
  yamlio.py      strict YAML loader (core-schema scalars, duplicate keys rejected)
  schemas/       template.v0.schema.json, profile_constraints.v0.schema.json
  reserved_duckdb.py  DuckDB's reserved keywords, written by scripts/make_reserved_words.py
  reserved.py    each dialect's reserved words; how an identifier slot value is written
  slots.py       Slot, value checks per slot type, placeholder scan, substitution,
                 SQL and Python rendering of values
  template.py    Template and ProfileConstraints (the loaded, valid form)
  validate.py    validate(), load_template(), schema access
  render.py      render(), resolve_slot_values()
  runner.py      run_tests(), transpile_to_duckdb(), table comparison
  scaffold.py    new_template()
  cli.py         emo-template (argparse); __main__.py calls it
```

Imports only point down this list (a module imports modules above it, never below), so
`cli` depends on everything and `spec` on nothing. `tests/test_layers.py` enforces the
order; a new module gets a place in it. New behavior goes in the lowest module that can
own it.

## Data flow

```
template dir ──validate()──> list[Problem]
     │
     └──load_template()──> Template ──render(values)──> entry text
                               │
run_tests(dir): validate ─> load_template ─> per case:
    slots.yaml ─> resolve values ─> render ─> [SQLGlot: platform dialect -> duckdb]
    ─> fresh DuckDB ─> per run: load input/*.parquet, execute, compare expected/*.parquet
    ─> CaseResult ─> RunReport
```

## Validation

`validate()` runs checks in a fixed order (manifest, entry, `cost.md`,
`profile_constraints.json`, tests tree) and appends problems to one report. Design rules:

- **Never raise.** Every input, however broken, produces problems. Each check guards the
  types it reads; a final `except Exception` turns a validator bug into one `internal`
  problem, and the fuzz tests assert that never happens.
- **No cascades.** A broken part suppresses only the checks that depend on it. A slot
  with an unknown type is still a known name, so references to it are not reported as
  undeclared; case values for it are not type-checked. Each fixture under
  `tests/fixtures/invalid/` must report exactly one code, which keeps this honest.
- **Schema first, semantics second.** JSON Schema covers structure and enums. Rules a
  schema cannot express well (id equals shape.platform, default vs. required, enum lists,
  slot usage, platform agreement between files, run numbering) are Python checks. Schema
  errors on `format`, `shape`, `platform` and slot `type` map to their own codes.
- **An unknown format stops everything.** A `format` from a newer version could change any
  rule, so nothing else is checked.
- **No execution.** The validator never runs SQL or Python. It renders the entry with
  stand-in values per slot type and asks SQLGlot (SQL, warning only) or `compile()`
  (Python, error) whether the result parses.

## Rendering

Substitution is a single regular expression over the entry text: `{{ name }}` with optional
spaces or tabs. Anything else that looks like template syntax is a validation error, so
there is no hidden logic in an entry file: what you read is what runs, plus values.
Values are checked by type before they are rendered. SQL rendering writes an identifier
quoted when the dialect reserves it (`reserved.py`, from lists that ship with the SDK) and
verbatim otherwise, leaves `expression` and enum values verbatim, parses each
`expressions` item and has SQLGlot write it back in the template's dialect (so the
rendered text is exactly one select-list item per entry), and asks SQLGlot for
dialect-correct string, boolean and interval literals; Python rendering produces Python
literals.

## Test runner

- DuckDB is the oracle. Each case gets a fresh in-memory database; runs share it, so
  stateful shapes (incremental, SCD2, CDC) can be tested across runs.
- Entries for other platforms are transpiled statement by statement with SQLGlot, with
  unsupported constructs raised as errors instead of silently dropped. A statement SQLGlot
  only understands as an opaque command is a failure, not a pass-through.
- Comparison is by column name, type family and row multiset (`EXCEPT ALL` both ways),
  done in DuckDB so that values are compared with DuckDB's casting rules.
- Python entries define `run(con)`; the runner execs the rendered module once per case and
  calls `run` once per run. They run only for platform `duckdb`.

## Dependencies

| Package    | Used for                                                 |
| ---------- | -------------------------------------------------------- |
| PyYAML     | reading `template.yaml` and `slots.yaml`                 |
| jsonschema | the two shipped schemas (Draft 2020-12)                  |
| SQLGlot    | expression checks, SQL literals, parsing, transpilation  |
| DuckDB     | running tests, reading and writing Parquet               |

All four are pinned through `uv.lock` for development and CI. SQLGlot upgrades can change
transpilation output, so they need the full gate and a look at the example and fixtures.
