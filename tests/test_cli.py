"""The emo-template command line."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import EXAMPLE, FAILING, INVALID, VALID
from emolysis_template_sdk.cli import main


def test_validate_ok(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", str(EXAMPLE)]) == 0
    assert capsys.readouterr().out.strip() == f"{EXAMPLE}: ok"


def test_validate_errors_exit_1(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", str(EXAMPLE), str(INVALID / "shape-unknown")]) == 1
    out = capsys.readouterr().out
    assert "error[shape-unknown]" in out
    assert "2 templates checked, 1 with errors" in out


def test_validate_warnings_exit_0(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", str(INVALID / "entry-sql-unparsable")]) == 0
    assert "ok, 1 warning" in capsys.readouterr().out


def test_validate_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", "--json", str(INVALID / "slot-unused")]) == 1
    payload = json.loads(capsys.readouterr().out)
    [template] = payload["templates"]
    assert template["ok"] is False
    assert [p["code"] for p in template["problems"]] == ["slot-unused"]


def test_test_passes(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["test", str(EXAMPLE)]) == 0
    out = capsys.readouterr().out
    assert "pass  known-totals  (2/2 runs)" in out
    assert out.strip().endswith("2 passed, 0 failed, 0 skipped")


def test_test_failure_exit_1(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["test", str(FAILING / "rows-mismatch")]) == 1
    out = capsys.readouterr().out
    assert "FAIL  basic" in out
    assert "error[rows-mismatch]" in out


def test_test_invalid_template_exit_1(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["test", str(INVALID / "tests-missing")]) == 1
    out = capsys.readouterr().out
    assert "not run: the template has validation errors" in out
    assert "1 template not run" in out


def test_test_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["test", "--json", str(VALID / "python-databricks")]) == 0
    payload = json.loads(capsys.readouterr().out)
    [template] = payload["templates"]
    assert template["cases"][0]["status"] == "skipped"


def test_new_then_validate_and_test(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    target = tmp_path / "scd2"
    assert main(["new", "scd2", "databricks", str(target)]) == 0
    assert "created scd2.databricks" in capsys.readouterr().out
    assert main(["validate", str(target)]) == 0
    assert main(["test", str(target)]) == 0


def test_new_into_non_empty_dir_exit_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "file").write_text("x")
    assert main(["new", "scd2", "duckdb", str(tmp_path)]) == 1
    assert "not an empty directory" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["frobnicate"],
        ["validate"],
        ["new", "star-schema", "duckdb", "x"],
        ["new", "scd2", "bigquery", "x"],
        ["new", "scd2"],
    ],
)
def test_usage_errors_exit_2(argv: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    assert main(argv) == 2
    assert "usage:" in capsys.readouterr().err


def test_version_and_help_exit_0(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--version"]) == 0
    assert capsys.readouterr().out.startswith("emo-template ")
    assert main(["new", "--help"]) == 0
    assert "aggregation-gold" in capsys.readouterr().out


def test_test_help_warns_that_templates_run(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["test", "--help"]) == 0
    out = " ".join(capsys.readouterr().out.split())
    assert "executes each template's SQL and Python on this machine" in out
    assert "only on templates you trust" in out


def test_module_entry_point() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "emolysis_template_sdk", "validate", str(EXAMPLE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith(": ok")
