# AGENTS.md — template-sdk

The public Emolysis template SDK: the template folder format (v0, specified in
`docs/format.md`), the Python package `emolysis-template-sdk` with its validator,
renderer and DuckDB test runner, the `emo-template` CLI, and example templates. Use it
to write and test your own templates against format v0. The repository is public under
MIT.

## Read first

1. This file.
2. Shared standards: emolysis/rules (private) — `AGENTS.md` there links the standards
   every repo follows. If you have access.
3. `docs/architecture.md`, `docs/development.md`, `docs/contributing.md`, and
   `docs/format.md` (the normative format spec).
4. `ROADMAP.md` (honest assessment, current focus, gaps) and the latest entries in
   `log/devlog.md`.
5. `docs/specs/sdk.md` (library API and CLI contract) and `docs/format.md` for the area
   you are changing.

## Ground rules

- Work from specs in `docs/specs/` and `docs/format.md`, never from chat history. No
  spec, no code: open an issue labelled `needs-spec`.
- `task gate` green before you finish. Never weaken a check, lower a floor, or skip a
  test to get green.
- `docs/format.md` is normative. A format change updates, in the same change: the rules,
  the problem code table and the changelog in `docs/format.md`; the JSON Schemas in
  `src/emolysis_template_sdk/schemas/` if structure changes; `spec.py`; the validator;
  fixtures and tests.
- `validate()` never executes template code. Anything that does (`run_tests`,
  `emo-template test`) says so in its docs and help.
- `validate()` never raises. Every new validation failure mode gets a problem code in
  `docs/format.md` and a fixture directory `tests/fixtures/invalid/<code>/` that reports
  exactly that code and nothing else. Every new runner failure gets a directory in
  `tests/fixtures/failing/` or a test in `tests/test_runner.py`.
- Parquet fixtures come only from `scripts/make_fixtures.py` (`task fixtures`). Expected
  tables are written by hand from the inputs, never produced by running the template
  under test.
- Library code is typed (mypy strict). The public API is `emolysis_template_sdk.__all__`
  plus the CLI; changing either updates `docs/specs/sdk.md`.
- Every change ships with tests.
- Public/private boundary: this repository is public. Nothing about internal
  architecture, private repos or third-party origins. Describe the format and the SDK in
  their own terms.

## Picking work

`ROADMAP.md` → Current focus → Gaps → `log/devlog.md` "Still open". Prefer the top item.

## Parallel agents

- One worktree per agent (`git worktree add ../template-sdk-<topic> -b <area>/<topic>`),
  own `.venv` (`task setup` in the worktree). Branches are `<area>/<topic>`, lower-case
  kebab, with the areas listed under "Before you finish".
- Edit only files you own for the task; new things go in new modules, not shared files.
- Shared manifests (`pyproject.toml`, `uv.lock`, `Taskfile.yml`, `docs/format.md`) get
  surgical edits.
- If someone else's change breaks the tree, do not fix their files; wait or report.

## Before you finish

1. `task gate` passes.
2. Add an entry at the top of `log/devlog.md` in the shared devlog format: heading
   `## <YYYY-MM-DD> · <area>: <what landed>` with `(green)` when the gate passed, then
   Landed, Numbers, Decisions (when made), Still open, Next (optional).
3. Commit as `<area>: <what>` (append `(green)` when the gate passed). Areas: `format`,
   `validate`, `render`, `runner`, `cli`, `scaffold`, `examples`, `fixtures`, `docs`,
   `ci`.

## Commands

| Command               | What it does                                                         |
| --------------------- | -------------------------------------------------------------------- |
| `task setup`          | `uv sync --locked` into `.venv`                                      |
| `task gate`           | lint, typecheck, test, fixtures:check, examples, package; what CI runs |
| `task fmt`            | ruff format and ruff check --fix, in place                           |
| `task lint`           | ruff format --check and ruff check                                   |
| `task typecheck`      | mypy strict on `src/`, `scripts/`, `tests/`                          |
| `task test`           | pytest including hypothesis fuzz; `task test -- -k render` to filter |
| `task fixtures`       | rewrite every Parquet fixture from `scripts/make_fixtures.py`        |
| `task fixtures:check` | fail if a committed fixture differs from its definition              |
| `task examples`       | `emo-template validate` and `test` on every example                  |
| `task package`        | build the wheel in a temp dir and check it ships the schemas         |
| `uv run emo-template` | the CLI from the working tree                                        |
