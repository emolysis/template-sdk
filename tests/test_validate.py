"""Validator: one fixture directory per failure mode, plus cases that need generated files."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest

from conftest import EXAMPLE, FAILING, INVALID, REPO, VALID, subdirs
from emolysis_template_sdk import (
    Problem,
    Template,
    TemplateError,
    errors,
    load_template,
    validate,
)

WARNING_CODES = {"entry-sql-unparsable"}


def codes(problems: list[Problem]) -> set[str]:
    return {p.code for p in problems}


@pytest.mark.parametrize("template", [EXAMPLE, *subdirs(VALID)], ids=lambda p: p.name)
def test_valid_templates_have_no_problems(template: Path) -> None:
    assert validate(template) == []


@pytest.mark.parametrize("template", subdirs(FAILING), ids=lambda p: p.name)
def test_failing_fixtures_are_valid_templates(template: Path) -> None:
    # They fail only when run; the validator may warn but must not error.
    assert errors(validate(template)) == []


@pytest.mark.parametrize("fixture", subdirs(INVALID), ids=lambda p: p.name)
def test_each_invalid_fixture_reports_exactly_its_code(fixture: Path) -> None:
    problems = validate(fixture)
    assert codes(problems) == {fixture.name}, [str(p) for p in problems]
    expected = "warning" if fixture.name in WARNING_CODES else "error"
    assert {p.severity for p in problems} == {expected}


def test_problem_codes_are_documented_and_covered() -> None:
    text = (REPO / "docs" / "format.md").read_text(encoding="utf-8")
    rows = re.findall(r"^\| `([a-z0-9-]+)` \| (error|warning) \| (validate|test) \|", text, re.M)
    documented = {code: stage for code, _, stage in rows}
    assert documented, "docs/format.md has no problem code table"
    covered_here = {"template-dir-missing", "entry-unreadable", "io-error", "internal"}
    covered_by_runner_tests = {
        "transpile-failed",
        "run-failed",
        "table-missing",
        "columns-mismatch",
        "rows-mismatch",
        "python-run-missing",
        "python-entry-skipped",
        "input-unreadable",
        "compare-failed",
    }
    fixtures = {p.name for p in subdirs(INVALID)}
    validate_codes = {c for c, stage in documented.items() if stage == "validate"}
    test_codes = {c for c, stage in documented.items() if stage == "test"}
    assert validate_codes - covered_here == fixtures
    assert test_codes == covered_by_runner_tests


def test_missing_directory(tmp_path: Path) -> None:
    problems = validate(tmp_path / "nope")
    assert codes(problems) == {"template-dir-missing"}
    file_path = tmp_path / "file.txt"
    file_path.write_text("x")
    assert codes(validate(file_path)) == {"template-dir-missing"}


def test_entry_that_is_not_utf8(minimal: Path) -> None:
    (minimal / "template.sql").write_bytes(b"SELECT '\xff\xfe' FROM {{ source_table }}")
    assert codes(validate(minimal)) == {"entry-unreadable"}


def test_unreadable_manifest_bytes(minimal: Path) -> None:
    (minimal / "template.yaml").write_bytes(b"\xff\xfe\x00")
    assert codes(validate(minimal)) == {"yaml-invalid"}


def test_duplicate_yaml_keys_are_rejected_with_a_line(minimal: Path) -> None:
    manifest = minimal / "template.yaml"
    manifest.write_text(manifest.read_text() + "version: 0.2.0\n")
    problems = validate(minimal)
    assert codes(problems) == {"yaml-invalid"}
    assert problems[0].line is not None
    assert "duplicate key" in problems[0].message


def test_yaml_is_read_with_core_schema_scalars(minimal: Path) -> None:
    manifest = minimal / "template.yaml"
    manifest.write_text(
        manifest.read_text()
        + "  - name: flag\n    type: string\n    default: no\n"
        + "  - name: day\n    type: string\n    default: 2026-10-12\n"
    )
    (minimal / "template.sql").write_text(
        "CREATE OR REPLACE TABLE {{ target_table }} AS\n"
        "SELECT *, {{ flag }} AS flag, {{ day }} AS day FROM {{ source_table }};\n"
    )
    assert validate(minimal) == []
    template = load_template(minimal)
    slot = template.slot("flag")
    assert slot is not None
    assert slot.default == "no"
    day = template.slot("day")
    assert day is not None
    assert day.default == "2026-10-12"


def test_extension_keys_are_allowed(minimal: Path) -> None:
    manifest = minimal / "template.yaml"
    manifest.write_text("x-owner: data-team\n" + manifest.read_text())
    constraints = minimal / "profile_constraints.json"
    data = json.loads(constraints.read_text())
    data["x-note"] = "anything"
    constraints.write_text(json.dumps(data))
    assert validate(minimal) == []


def test_unknown_manifest_key_is_rejected(minimal: Path) -> None:
    manifest = minimal / "template.yaml"
    manifest.write_text("owner: data-team\n" + manifest.read_text())
    problems = validate(minimal)
    assert codes(problems) == {"manifest-invalid"}
    assert "owner" in problems[0].message


def test_non_string_keys_do_not_crash(minimal: Path) -> None:
    manifest = minimal / "template.yaml"
    manifest.write_text("1: one\n" + manifest.read_text())
    assert codes(validate(minimal)) == {"manifest-invalid"}


def test_hidden_files_are_ignored(minimal: Path) -> None:
    (minimal / "tests" / ".DS_Store").write_text("x")
    (minimal / "tests" / "basic" / "runs" / "01" / "input" / ".gitkeep").write_text("")
    assert validate(minimal) == []


def test_markdown_notes_are_allowed_in_tests(minimal: Path) -> None:
    (minimal / "tests" / "README.md").write_text("# Cases\n")
    (minimal / "tests" / "basic" / "notes.md").write_text("Why this case exists.\n")
    assert validate(minimal) == []


def test_input_dir_may_be_empty(minimal: Path) -> None:
    run = minimal / "tests" / "basic" / "runs" / "02"
    (run / "input").mkdir(parents=True)
    shutil.copytree(minimal / "tests" / "basic" / "runs" / "01" / "expected", run / "expected")
    assert validate(minimal) == []


def test_gap_in_run_numbers(minimal: Path) -> None:
    runs = minimal / "tests" / "basic" / "runs"
    shutil.copytree(runs / "01", runs / "03")
    problems = validate(minimal)
    assert codes(problems) == {"runs-malformed"}
    assert "01, 03" in problems[0].message


def test_empty_slots_file_means_no_values(minimal: Path) -> None:
    manifest = minimal / "template.yaml"
    manifest.write_text(manifest.read_text().replace("required: true", "default: source", 1))
    (minimal / "tests" / "basic" / "slots.yaml").write_text("target_table: target\n")
    assert validate(minimal) == []
    (minimal / "tests" / "basic" / "slots.yaml").write_text("")
    assert codes(validate(minimal)) == {"slot-missing"}


def test_format_unsupported_stops_other_checks(minimal: Path) -> None:
    manifest = minimal / "template.yaml"
    manifest.write_text(manifest.read_text().replace("/v0", "/v1"))
    (minimal / "cost.md").unlink()
    shutil.rmtree(minimal / "tests")
    assert codes(validate(minimal)) == {"format-unsupported"}


def test_several_problems_are_reported_together(minimal: Path) -> None:
    (minimal / "cost.md").unlink()
    (minimal / "tests" / "basic" / "slots.yaml").write_text("source_table: 12\n")
    assert codes(validate(minimal)) == {"cost-missing", "slot-value-invalid", "slot-missing"}


def test_requires_and_forbids_must_not_overlap(minimal: Path) -> None:
    constraints = minimal / "profile_constraints.json"
    data = json.loads(constraints.read_text())
    data["requires"] = ["delta"]
    data["forbids"] = ["delta"]
    constraints.write_text(json.dumps(data))
    problems = validate(minimal)
    assert codes(problems) == {"constraints-invalid"}
    assert "delta" in problems[0].message


def test_constraints_duplicate_json_key(minimal: Path) -> None:
    (minimal / "profile_constraints.json").write_text(
        '{"platform": "duckdb", "platform": "duckdb", "profile_version": ">=1",'
        ' "requires": [], "forbids": []}'
    )
    assert codes(validate(minimal)) == {"constraints-invalid"}


def test_problem_rendering() -> None:
    problem = Problem("slot-unused", "slot 'x' is declared but never used", "template.yaml", 4)
    assert str(problem) == "template.yaml:4: error[slot-unused] slot 'x' is declared but never used"
    assert problem.to_dict()["line"] == 4
    assert str(Problem("template-dir-missing", "gone")) == ".: error[template-dir-missing] gone"


def test_load_template_returns_a_template() -> None:
    template = load_template(EXAMPLE)
    assert isinstance(template, Template)
    assert template.id == "aggregation-gold.duckdb"
    assert template.language == "sql"
    assert template.dialect == "duckdb"
    assert [s.name for s in template.slots][:2] == ["source_table", "target_table"]
    assert template.constraints.platform == "duckdb"
    assert template.slot("missing") is None


def test_fabric_reads_as_spark() -> None:
    assert load_template(VALID / "fabric-sql").dialect == "spark"


def test_load_template_raises_with_problems() -> None:
    with pytest.raises(TemplateError) as raised:
        load_template(INVALID / "shape-unknown")
    assert codes(raised.value.problems) == {"shape-unknown"}
    assert "shape-unknown" in str(raised.value)


def test_load_template_ignores_tests_tree() -> None:
    template = load_template(INVALID / "tests-missing")
    assert template.id == "snapshot.duckdb"
