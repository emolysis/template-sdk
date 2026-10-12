"""`emo-template` command line.

Exit codes: 0 success, 1 the templates have errors or tests failed (or the command could
not complete), 2 usage error.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from importlib import metadata
from pathlib import Path
from typing import TextIO

from .problems import Problem, errors
from .runner import RunReport, run_tests
from .scaffold import new_template
from .spec import PLATFORMS, SHAPES
from .validate import validate

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2


def _version() -> str:
    try:
        return metadata.version("emolysis-template-sdk")
    except metadata.PackageNotFoundError:
        return "unknown"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="emo-template",
        description="Validate, scaffold and test Emolysis pipeline templates (format v0).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {_version()}")
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    check = commands.add_parser("validate", help="check template directories against format v0")
    check.add_argument("dirs", nargs="+", type=Path, metavar="DIR")
    check.add_argument("--json", action="store_true", help="print a JSON report")

    new = commands.add_parser(
        "new",
        help="write a valid template skeleton",
        description="Write a valid template skeleton with one passing test case.",
        epilog=f"shapes: {', '.join(SHAPES)}; platforms: {', '.join(PLATFORMS)}",
    )
    new.add_argument("shape", choices=list(SHAPES), metavar="SHAPE")
    new.add_argument("platform", choices=list(PLATFORMS), metavar="PLATFORM")
    new.add_argument("dir", type=Path, metavar="DIR")

    test = commands.add_parser(
        "test",
        help="run the test cases of templates on DuckDB",
        description=(
            "Run the test cases of templates on DuckDB. This executes each template's SQL "
            "and Python on this machine with your privileges (files, extensions, network); "
            "run it only on templates you trust. `validate` never executes them."
        ),
    )
    test.add_argument("dirs", nargs="+", type=Path, metavar="DIR")
    test.add_argument("--json", action="store_true", help="print a JSON report")
    return parser


def _print_problems(problems: Sequence[Problem], out: TextIO, indent: str = "  ") -> None:
    for problem in problems:
        lines = str(problem).splitlines() or [""]
        print(f"{indent}{lines[0]}", file=out)
        for extra in lines[1:]:
            print(f"{indent}    {extra}", file=out)


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" + ("" if count == 1 else "s")


def _cmd_validate(dirs: Sequence[Path], as_json: bool, out: TextIO) -> int:
    results = [(directory, validate(directory)) for directory in dirs]
    failed = sum(1 for _, problems in results if errors(problems))
    if as_json:
        payload = {
            "templates": [
                {
                    "path": str(directory),
                    "ok": not errors(problems),
                    "problems": [p.to_dict() for p in problems],
                }
                for directory, problems in results
            ]
        }
        print(json.dumps(payload, indent=2), file=out)
    else:
        for directory, problems in results:
            error_count = len(errors(problems))
            warning_count = len(problems) - error_count
            if not problems:
                print(f"{directory}: ok", file=out)
                continue
            status = "ok" if not error_count else _plural(error_count, "error")
            if warning_count:
                status += f", {_plural(warning_count, 'warning')}"
            print(f"{directory}: {status}", file=out)
            _print_problems(problems, out)
        if len(results) > 1:
            print(f"{_plural(len(results), 'template')} checked, {failed} with errors", file=out)
    return EXIT_FAILED if failed else EXIT_OK


def _print_report(report: RunReport, out: TextIO) -> None:
    label = f" ({report.template_id})" if report.template_id else ""
    print(f"{report.path}{label}", file=out)
    if report.template_id is None:
        _print_problems(report.problems, out)
        print("  not run: the template has validation errors", file=out)
        return
    _print_problems(report.problems, out)
    for case in report.cases:
        word = {"passed": "pass", "failed": "FAIL", "skipped": "skip"}[case.status]
        print(f"  {word}  {case.name}  ({case.runs_passed}/{case.runs_total} runs)", file=out)
        _print_problems(case.problems, out, indent="        ")


def _cmd_test(dirs: Sequence[Path], as_json: bool, out: TextIO) -> int:
    reports = [run_tests(directory) for directory in dirs]
    if as_json:
        print(json.dumps({"templates": [r.to_dict() for r in reports]}, indent=2), file=out)
    else:
        for report in reports:
            _print_report(report, out)
        passed = sum(r.count("passed") for r in reports)
        failed = sum(r.count("failed") for r in reports)
        skipped = sum(r.count("skipped") for r in reports)
        invalid = sum(1 for r in reports if r.template_id is None)
        summary = f"{passed} passed, {failed} failed, {skipped} skipped"
        if invalid:
            summary += f", {_plural(invalid, 'template')} not run"
        print(summary, file=out)
    return EXIT_OK if all(r.ok for r in reports) else EXIT_FAILED


def _cmd_new(shape: str, platform: str, directory: Path, out: TextIO, err: TextIO) -> int:
    try:
        root = new_template(shape, platform, directory)
    except FileExistsError as exc:
        print(f"emo-template new: {exc}", file=err)
        return EXIT_FAILED
    except OSError as exc:
        print(f"emo-template new: {exc}", file=err)
        return EXIT_FAILED
    print(f"created {shape}.{platform} in {root}", file=out)
    print(
        f"next: edit template.sql, cost.md and tests/basic, then run: emo-template test {root}",
        file=out,
    )
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return its exit code."""
    logging.getLogger("sqlglot").setLevel(logging.ERROR)
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exc:  # argparse exits 2 on usage errors, 0 on --help/--version
        return exc.code if isinstance(exc.code, int) else EXIT_USAGE
    out, err = sys.stdout, sys.stderr
    if args.command == "validate":
        return _cmd_validate(args.dirs, args.json, out)
    if args.command == "test":
        return _cmd_test(args.dirs, args.json, out)
    if args.command == "new":
        return _cmd_new(args.shape, args.platform, args.dir, out, err)
    return EXIT_USAGE  # unreachable: argparse requires a command


if __name__ == "__main__":
    raise SystemExit(main())
