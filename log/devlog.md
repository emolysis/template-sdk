# Devlog — template-sdk

Newest entry first. Format: `standards/devlog.md` in emolysis/rules (private).

## 2026-10-25 · render: identifier slot values that the dialect reserves are written quoted (green)

- Landed: an `identifier`, `column`, `columns` item or `table` part that the template's dialect reserves is written as a quoted identifier in the case the dialect gives the unquoted name: `order` is `"ORDER"` on Snowflake and `"order"` on DuckDB; Databricks and Spark write every value verbatim. `docs/format.md` section 4 ("Identifiers and reserved words"), the slot types table and the changelog.
- Landed: `reserved.py` holds Snowflake's 92 keywords, copied from its reserved-keywords page (read 2026-10-25); `reserved_duckdb.py` holds DuckDB's 75 `reserved` keywords, written by `scripts/make_reserved_words.py` from `duckdb_keywords()` (DuckDB 1.5.6). `task reserved` rewrites it and `task reserved:check`, in the gate, fails when the installed DuckDB differs.
- Landed: `tests/fixtures/renders/` holds every example's and valid fixture's render per test case from the renderer before this change; a test checks they render byte for byte the same.
- Numbers: 578 tests pass (+242): exact strings per dialect, each part of a table name, each item of `columns`, every DuckDB word failing bare and working quoted on DuckDB, every Snowflake word parsing as its upper-case quoted column, the DuckDB example run on columns named `group` and `order`, a Snowflake render transpiled and run on DuckDB, 9 renders unchanged.
- Decisions: the lists ship with the SDK and are never read from a database at render time; quoting is identity-preserving, so a list may hold a word the platform would accept bare. `expression` and `expressions` values are not quoted. Spark's `enforceReservedKeywords` set to `true` is outside v0's guarantee.
- Still open: a Snowflake object created with a quoted lower- or mixed-case name cannot be named by a slot value.

## 2026-10-23 · ci: a draft pull request runs its checks when it is marked ready (green)

- Landed: `ci.yml` lists `ready_for_review` in its `pull_request` types; its jobs skip drafts, and the default types never fire when a draft is marked ready, so a draft ran nothing until its next push.
- Numbers: one workflow line.
- Still open: none.

## 2026-10-20 · ci: minute saving in the workflows

- Landed: `ci.yml` ignores `log/**`, `ROADMAP.md`, `docs/product/**`, `AGENTS.md` and
  `CLAUDE.md` on push and pull request (the tests read `docs/format.md` and the specs,
  which stay in), cancels the run a newer push supersedes on every ref, and skips draft
  pull requests; `claude-review.yml` reviews once per pull request (`opened`,
  `ready_for_review`, the `review` label), never on every push; the `review` label.
  Workflow files only; validated with actionlint, the gate was not run.
- Numbers: three workflow files, one label.
- Still open: lands with the next pull request; no pull request while the freeze holds.

## 2026-10-18 · docs: present tense for public copy (green)

- Landed: the present-tense lines follow the founder's Notion page word for word
  ("Emolysis puts a team of agents at your direction from your laptop"; "Direct a team of
  agents from your laptop").
- Landed: the README intro and the "What we are building" block in `AGENTS.md` describe
  Emolysis in the present tense (founder decision of 2026-10-18); availability stays a
  status line ("not yet available").
- Numbers: docs only.
- Still open: none.

## 2026-10-18 · docs: architecture review in AGENTS.md (green)

- Landed: one ground rule in `AGENTS.md`: a contract change is checked with the architect
  session before code; milestones and deviations are reported to it (emolysis/rules
  `standards/architecture-review.md`).
- Numbers: docs only.
- Still open: none.

## 2026-10-18 · docs: the new positioning (green)

- Landed: `README.md` and `AGENTS.md` open with the positioning: "An entire data team. One
  download.", the agentic lakehouse for data engineering and analytics, a team of agents
  you direct from your laptop. Unreleased things stay in the future tense; status unchanged.
- Numbers: docs only.
- Still open: none.

## 2026-10-12 · format: slot type `expressions`, example on `group_by` and `measures` (green)

- Landed: slot type `expressions` (list of SQL expressions with optional aliases; each item rewritten by SQLGlot in the template's dialect, joined with `, `; Python list of strings) in `docs/format.md` section 4, `spec.py`, `template.v0.schema.json` and `slots.py`; per-dialect literal table for `string`, `boolean`, `duration` in `docs/format.md`.
- Landed: `examples/aggregation-gold-duckdb` now declares exactly `source_table`, `target_table`, `group_by` (columns), `measures` (expressions); its fixtures redefined in `scripts/make_fixtures.py`; `tests/fixtures/valid/databricks-sql` uses the same slots with Spark SQL measures.
- Landed: warning that `emo-template test` executes template SQL and Python (README, `docs/format.md` section 8, `docs/writing-templates.md`, `docs/architecture.md`, `test --help`); README and AGENTS no longer claim a shipped library; branches are `<area>/<topic>`.
- Numbers: 336 tests pass (+70), 8 of them hypothesis fuzz tests (+3: `expressions` check totality, one select item per entry plus idempotent rewrite, string literal round trip in duckdb, databricks, snowflake, spark); 108 Parquet fixtures match; 51 problem codes (unchanged).
- Decisions: `expressions` items follow the `expression` rules (no `;`, no clause, no bare query) plus an optional alias; comments are dropped when rewritten; duplicate aliases are not checked. See `docs/format.md` section 4.
- Decisions: no sandbox for `emo-template test`; documented instead (`docs/architecture.md`).
- Still open: per-shape required slots are not part of the format; see `ROADMAP.md` Gaps.
- Next: one example per production platform (`ROADMAP.md` Current focus 1).

## 2026-10-12 · scaffold: format v0, SDK, CLI and example (green)

- Landed: template format v0 spec (`docs/format.md`) and JSON Schemas as package data; `emolysis_template_sdk` with `validate`, `load_template`, `render`, `run_tests`, `new_template`; `emo-template validate|new|test` (exit 0/1/2, `--json`); example `examples/aggregation-gold-duckdb` (2 cases, 3 runs); `scripts/make_fixtures.py`; docs (format, writing templates, architecture, development, contributing, `docs/specs/sdk.md`); CI running `task setup` and `task gate`.
- Numbers: 266 tests pass, 5 of them hypothesis fuzz tests; 51 problem codes (42 validate, 9 test); 38 invalid, 8 failing and 7 valid fixtures; 108 Parquet fixtures checked by `task fixtures:check`; mypy strict clean.
- Decisions: YAML read with core-schema scalars; slots are required xor defaulted; `fabric` entries are Spark SQL; Python entries run locally only for `duckdb`; comparison by column name, type family and row multiset. See `docs/format.md`.
- Still open: platform-only statements, Fabric T-SQL templates, PyPI release; see `ROADMAP.md` Gaps.
- Next: one template per production platform as examples (`ROADMAP.md` Current focus).
