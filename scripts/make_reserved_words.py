"""Write or check DuckDB's reserved keywords in src/emolysis_template_sdk/reserved_duckdb.py.

The list is the `reserved` category of `duckdb_keywords()` in the DuckDB this
environment has installed. The renderer reads the committed module and never asks DuckDB
at render time.

    uv run python scripts/make_reserved_words.py          # write the module
    uv run python scripts/make_reserved_words.py --check  # compare it with the installed DuckDB
"""

from __future__ import annotations

import argparse
import datetime
import importlib.util
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
MODULE = ROOT / "src" / "emolysis_template_sdk" / "reserved_duckdb.py"
SOURCE = "https://duckdb.org/docs/stable/sql/dialect/keywords_and_identifiers"


def reserved_words() -> list[str]:
    """The installed DuckDB's reserved keywords, sorted."""
    con = duckdb.connect()
    try:
        rows = con.execute(
            "SELECT keyword_name FROM duckdb_keywords() WHERE keyword_category = 'reserved'"
        ).fetchall()
    finally:
        con.close()
    return sorted(str(row[0]) for row in rows)


def module_text(words: list[str], version: str, read: str) -> str:
    """The module's source for `words`, read from DuckDB `version` on the date `read`."""
    lines = [
        '"""DuckDB\'s reserved keywords, written by scripts/make_reserved_words.py; do not edit.',
        "",
        f"The `reserved` category of `duckdb_keywords()` in DuckDB {version}, read {read}.",
        "DuckDB documents the function and the categories at",
        f"{SOURCE}.",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        f'DUCKDB_VERSION = "{version}"',
        '"""The DuckDB version the list was read from."""',
        "",
        f'DUCKDB_READ = "{read}"',
        '"""The date the list was read."""',
        "",
        "DUCKDB_RESERVED: frozenset[str] = frozenset(",
        "    {",
        *[f'        "{word}",' for word in words],
        "    }",
        ")",
        '"""DuckDB\'s reserved keywords, in lower case as DuckDB lists them."""',
        "",
    ]
    return "\n".join(lines)


def committed() -> tuple[frozenset[str], str]:
    """The words and the DuckDB version the committed module holds."""
    spec = importlib.util.spec_from_file_location("reserved_duckdb", MODULE)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load {MODULE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    words: frozenset[str] = module.DUCKDB_RESERVED
    version: str = module.DUCKDB_VERSION
    return words, version


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--check", action="store_true", help="compare instead of writing")
    args = parser.parse_args(argv)
    words = reserved_words()
    if args.check:
        held, version = committed()
        if held == frozenset(words) and version == duckdb.__version__:
            print(f"{MODULE.relative_to(ROOT)}: {len(words)} words, DuckDB {version}")
            return 0
        print(
            f"{MODULE.relative_to(ROOT)} holds {len(held)} words from DuckDB {version}; "
            f"DuckDB {duckdb.__version__} reserves {len(words)}. Run `task reserved`.",
            file=sys.stderr,
        )
        return 1
    read = datetime.datetime.now(datetime.UTC).date().isoformat()
    MODULE.write_text(module_text(words, duckdb.__version__, read))
    print(f"wrote {MODULE.relative_to(ROOT)}: {len(words)} words, DuckDB {duckdb.__version__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
