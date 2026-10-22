"""Immutable, collection-independent generation identities and previews.

Keys are note type plus character/component, never a stored synthetic ID.
Source note IDs deliberately never enter these contracts. Keys use NFC,
not compatibility normalization: visually related CJK forms may be distinct.
"""

import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal

NOTE_TYPES = (
    "kanji-recognition",
    "kanji-production",
    "primitive-recognition",
    "primitive-production",
)


@dataclass(frozen=True, order=True)
class Identity:
    note_type: str
    key: str

    def __post_init__(self):
        if self.note_type not in NOTE_TYPES:
            raise ValueError("Unknown Katanki note type.")
        if not isinstance(self.key, str) or not self.key or self.key != self.key.strip():
            raise ValueError("Character/component key must be nonempty without surrounding spaces.")
        object.__setattr__(self, "key", unicodedata.normalize("NFC", self.key))
        if self.kind == "kanji" and len(self.key) != 1:
            raise ValueError("Kanji notes require one character.")

    @property
    def kind(self) -> str:
        return self.note_type.split("-", 1)[0]


@dataclass(frozen=True)
class LearningUnit:
    identity: Identity
    prerequisites: tuple[Identity, ...] = ()
    # Graphical label is not a dictionary radical or a mnemonic name.
    label: str = ""
    unavailable_reason: str = ""


@dataclass(frozen=True)
class PlanItem:
    unit: LearningUnit
    outcome: Literal["create", "skip", "unavailable"]
    reason: str


@dataclass(frozen=True)
class GenerationPlan:
    items: tuple[PlanItem, ...]


def prerequisite_order(units: Mapping[Identity, LearningUnit]) -> tuple[Identity, ...]:
    """Deterministic topological order; reject incomplete or cyclic input."""
    ordered = []
    active = set()
    done = set()

    def visit(identity):
        if identity in active:
            raise ValueError(f"Component cycle at {identity}")
        if identity in done:
            return
        if identity not in units:
            raise ValueError(f"Missing component node: {identity}")
        if units[identity].identity != identity:
            raise ValueError("Component graph key does not match its unit identity.")
        active.add(identity)
        for prerequisite in sorted(set(units[identity].prerequisites)):
            visit(prerequisite)
        active.remove(identity)
        done.add(identity)
        ordered.append(identity)

    for identity in sorted(units):
        visit(identity)
    return tuple(ordered)


def plan_generation(
    units: Iterable[LearningUnit],
    existing: Iterable[Identity],
    *,
    include_primitives: bool,
) -> GenerationPlan:
    """No host calls, mutations, implicit updates or source lifecycle tracking."""
    graph = {}
    for unit in units:
        previous = graph.get(unit.identity)
        if previous is not None and previous != unit:
            raise ValueError("Conflicting definitions for the same learning identity.")
        graph[unit.identity] = unit
    if not include_primitives:
        graph = {
            identity: LearningUnit(identity, (), unit.label, unit.unavailable_reason)
            for identity, unit in graph.items()
            if identity.kind == "kanji"
        }
    existing = set(existing)
    unavailable = set()
    items = []
    for identity in prerequisite_order(graph):
        unit = graph[identity]
        if identity in existing:
            outcome, reason = "skip", "Owned note already exists; preserve all edits and progress."
        elif unit.unavailable_reason:
            outcome, reason = "unavailable", unit.unavailable_reason
        elif any(parent in unavailable for parent in unit.prerequisites):
            outcome, reason = "unavailable", "A prerequisite is unavailable."
        else:
            outcome, reason = "create", "No owned note with this identity."
        if outcome == "unavailable":
            unavailable.add(identity)
        items.append(PlanItem(unit, outcome, reason))
    return GenerationPlan(tuple(items))
