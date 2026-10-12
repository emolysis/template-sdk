"""Check that a built wheel ships the package data the SDK needs at run time.

uv run python scripts/check_wheel.py DIST_DIR
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

REQUIRED = (
    "emolysis_template_sdk/schemas/template.v0.schema.json",
    "emolysis_template_sdk/schemas/profile_constraints.v0.schema.json",
    "emolysis_template_sdk/py.typed",
)


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    wheels = sorted(Path(argv[0]).glob("*.whl"))
    if len(wheels) != 1:
        print(f"expected one wheel in {argv[0]}, found {len(wheels)}", file=sys.stderr)
        return 1
    with zipfile.ZipFile(wheels[0]) as wheel:
        names = set(wheel.namelist())
    missing = [name for name in REQUIRED if name not in names]
    for name in missing:
        print(f"{wheels[0].name} is missing {name}", file=sys.stderr)
    if not missing:
        print(f"{wheels[0].name}: package data present")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
