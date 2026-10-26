"""List-ordered coverage sections; overlapping targets never inflate a scope."""

import unicodedata
from dataclasses import dataclass

from .progress import STATES, ProgressSnapshot
from .targets import TargetRegistry

STATE_SORT_ORDER = ("mature", "young", "relearning", "learning", "new", "missing")

LABELS = {
    "missing": "Missing cards",
    "new": "New",
    "learning": "Learning",
    "young": "Young",
    "mature": "Mature",
    "relearning": "Relearning",
}


@dataclass(frozen=True)
class CoverageSection:
    key: tuple[str, str | None]
    title: str
    characters: tuple[str, ...]
    parent: tuple[str, str | None] | None = None


def coverage_sections(
    registry: TargetRegistry, progress: ProgressSnapshot | None = None
) -> tuple[CoverageSection, ...]:
    sections = [
        CoverageSection(
            ("", None),
            "All enabled lists",
            registry.targets(tuple((target.id, None) for target in registry.lists)),
        )
    ]
    if progress is not None:
        sections.append(
            CoverageSection(
                ("@cards", None),
                "All kanji with cards",
                tuple(dict.fromkeys(card.character for card in progress.cards)),
            )
        )
    if progress is not None:
        parent = ("@discovered", None)
        sections.append(
            CoverageSection(
                parent,
                "All discovered kanji",
                tuple(
                    dict.fromkeys(
                        char
                        for _, _, characters in progress.discovered_decks
                        for char in characters
                    )
                ),
            )
        )
        sections.extend(
            CoverageSection(("@discovered", str(deck_id)), name, characters, parent)
            for deck_id, name, characters in progress.discovered_decks
            if characters
        )
    for target in registry.lists:
        parent = (target.id, None)
        sections.append(CoverageSection(parent, target.title, target.characters()))
        if len(target.groups) > 1:
            sections.extend(
                CoverageSection(
                    (target.id, group.id),
                    group.title,
                    group.characters,
                    parent,
                )
                for group in target.groups
            )
    return tuple(sections)


def counts_for(progress: ProgressSnapshot, characters: tuple[str, ...], mode: str) -> dict:
    return progress.payload(characters)["counts"][mode]


def normalize_search(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in text)


def count_description(counts: dict) -> str:
    return " · ".join(f"{LABELS[state]}: {counts[state]:,}" for state in STATES)
