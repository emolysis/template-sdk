"""The in-memory form of a valid template."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .slots import Slot
from .spec import DIALECTS, ENTRY_FILES, FORMAT_V0


@dataclass(frozen=True, slots=True)
class ProfileConstraints:
    """Contents of profile_constraints.json."""

    platform: str
    profile_version: str
    requires: tuple[str, ...] = ()
    forbids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Template:
    """A template directory that passed validation of its manifest, entry and constraints.

    Built by `load_template`. `source` is the entry file text before substitution.
    """

    path: Path
    id: str
    shape: str
    platform: str
    version: str
    title: str
    description: str
    entry: str
    slots: tuple[Slot, ...]
    source: str
    constraints: ProfileConstraints
    format: str = FORMAT_V0

    @property
    def language(self) -> str:
        """`sql` or `python`, from the entry file name."""
        return ENTRY_FILES[self.entry]

    @property
    def dialect(self) -> str:
        """SQLGlot dialect the entry is written in (fabric reads as `spark` in v0)."""
        return DIALECTS[self.platform]

    def slot(self, name: str) -> Slot | None:
        """Return the slot called `name`, or None."""
        for slot in self.slots:
            if slot.name == name:
                return slot
        return None
