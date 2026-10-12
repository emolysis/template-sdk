"""Rendering: substitute slot values into a template's entry file."""

from __future__ import annotations

from collections.abc import Mapping

from .problems import Problem, RenderError
from .slots import check_value, render_with
from .template import Template


def resolve_slot_values(
    template: Template, slot_values: Mapping[str, object] | None = None, path: str = ""
) -> tuple[dict[str, object], list[Problem]]:
    """Merge `slot_values` with slot defaults and check every value against its slot type.

    Returns the resolved values (one per declared slot when there are no problems) and
    the problems found. `path` is used as the location of the problems.
    """
    given = dict(slot_values or {})
    problems: list[Problem] = []
    declared = {slot.name for slot in template.slots}
    for key in given:
        if key not in declared:
            problems.append(Problem("slot-unknown", f"value for undeclared slot {key!r}", path))
    resolved: dict[str, object] = {}
    for slot in template.slots:
        if slot.name in given:
            value = given[slot.name]
        elif slot.has_default:
            value = slot.default
        else:
            problems.append(
                Problem("slot-missing", f"required slot {slot.name!r} has no value", path)
            )
            continue
        reason = check_value(slot, value, template.dialect)
        if reason is not None:
            problems.append(Problem("slot-value-invalid", f"{slot.name}: {reason}", path))
            continue
        resolved[slot.name] = value
    return resolved, problems


def render(template: Template, slot_values: Mapping[str, object] | None = None) -> str:
    """Return the entry file with every `{{ slot }}` replaced by its rendered value.

    Missing values fall back to slot defaults. Raises `RenderError` when a required slot
    has no value, a value names an undeclared slot, or a value does not fit its slot type.
    See docs/format.md ("Substitution") for how each slot type renders in SQL and Python.
    """
    resolved, problems = resolve_slot_values(template, slot_values)
    if problems:
        raise RenderError(problems)
    return render_with(
        template.source, template.slots, resolved, template.language, template.dialect
    )
