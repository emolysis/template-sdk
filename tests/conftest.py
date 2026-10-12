"""Shared paths and helpers for the test suite."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
FIXTURES = REPO / "tests" / "fixtures"
VALID = FIXTURES / "valid"
INVALID = FIXTURES / "invalid"
FAILING = FIXTURES / "failing"
EXAMPLES = REPO / "examples"
EXAMPLE = EXAMPLES / "aggregation-gold-duckdb"


def subdirs(path: Path) -> list[Path]:
    return sorted(p for p in path.iterdir() if p.is_dir())


@pytest.fixture
def minimal(tmp_path: Path) -> Path:
    """A writable copy of tests/fixtures/valid/minimal."""
    target = tmp_path / "minimal"
    shutil.copytree(VALID / "minimal", target)
    return target


def copy_fixture(source: Path, tmp_path: Path) -> Path:
    target = tmp_path / source.name
    shutil.copytree(source, target)
    return target
