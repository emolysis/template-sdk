"""Problems reported by the validator and test runner, and the exceptions that carry them."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

Severity = Literal["error", "warning"]


@dataclass(frozen=True, slots=True)
class Problem:
    """One finding about a template.

    `code` is a stable kebab-case id (see docs/format.md, "Problem codes"); `path` is
    relative to the template directory in POSIX form, or empty for the directory itself.
    """

    code: str
    message: str
    path: str = ""
    line: int | None = None
    severity: Severity = "error"

    @property
    def is_error(self) -> bool:
        return self.severity == "error"

    def location(self) -> str:
        if not self.path:
            return "."
        return self.path if self.line is None else f"{self.path}:{self.line}"

    def __str__(self) -> str:
        return f"{self.location()}: {self.severity}[{self.code}] {self.message}"

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "path": self.path,
            "line": self.line,
        }


def errors(problems: Iterable[Problem]) -> list[Problem]:
    """Return only the problems with severity `error`."""
    return [p for p in problems if p.is_error]


class TemplateError(Exception):
    """Raised by `load_template` when a template is not valid. Carries the problems."""

    def __init__(self, problems: Iterable[Problem]) -> None:
        self.problems = list(problems)
        summary = "; ".join(str(p) for p in self.problems[:3])
        more = len(self.problems) - 3
        if more > 0:
            summary += f"; and {more} more"
        super().__init__(summary or "invalid template")


class RenderError(TemplateError):
    """Raised by `render` when slot values are missing, unknown or of the wrong type."""
