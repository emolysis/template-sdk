"""`new_template` skeletons are valid for every shape and platform."""

from __future__ import annotations

from pathlib import Path

import pytest

from emolysis_template_sdk import PLATFORMS, SHAPES, new_template, run_tests, validate


@pytest.mark.parametrize("platform", list(PLATFORMS))
@pytest.mark.parametrize("shape", list(SHAPES))
def test_skeleton_is_valid(shape: str, platform: str, tmp_path: Path) -> None:
    root = new_template(shape, platform, tmp_path / "t")
    assert validate(root) == []
    assert f"id: {shape}.{platform}" in (root / "template.yaml").read_text()


@pytest.mark.parametrize("platform", list(PLATFORMS))
def test_skeleton_tests_pass(platform: str, tmp_path: Path) -> None:
    report = run_tests(new_template("snapshot", platform, tmp_path / "t"))
    assert report.ok
    assert [c.status for c in report.cases] == ["passed"]


def test_existing_empty_directory_is_fine(tmp_path: Path) -> None:
    assert validate(new_template("backfill", "duckdb", tmp_path)) == []


def test_bad_arguments(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown shape"):
        new_template("star-schema", "duckdb", tmp_path / "a")
    with pytest.raises(ValueError, match="unknown platform"):
        new_template("scd2", "bigquery", tmp_path / "b")
    (tmp_path / "c").write_text("x")
    with pytest.raises(FileExistsError):
        new_template("scd2", "duckdb", tmp_path / "c")
