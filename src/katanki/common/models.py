"""Normalized discovery, graphical component, and local dictionary contracts."""

from dataclasses import dataclass
from typing import Protocol

# Smaller values take precedence when several cards/notes match the same word.
WORD_STATUS_ORDER = {
    "learned": 0,
    "relearning": 1,
    "learning": 2,
    "new": 3,
    "exists": 3,
    "missing": 4,
}


@dataclass(frozen=True)
class ScanSelection:
    deck_ids: tuple[int, ...]
    note_type_id: int
    fields: tuple[str, ...]
    reading_field: str | None = None

    def __post_init__(self):
        if self.reading_field is not None and (
            not isinstance(self.reading_field, str) or not self.reading_field.strip()
        ):
            raise ValueError("Reading field names must not be empty.")
        if not self.deck_ids or not self.fields:
            raise ValueError("Select at least one deck and one field.")
        if any(type(value) is not int or value <= 0 for value in self.deck_ids):
            raise ValueError("Deck IDs must be positive integers.")
        if type(self.note_type_id) is not int or self.note_type_id <= 0:
            raise ValueError("Select a valid note type.")
        if any(not isinstance(field, str) or not field for field in self.fields):
            raise ValueError("Field names must not be empty.")


@dataclass(frozen=True)
class NoteText:
    fields: tuple[str, ...]
    tags: tuple[str, ...] = ()
    # Read-only snapshot; no source IDs or live card links are retained.
    word_status: str = "missing"
    field_readings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScanResult:
    scanned_notes: int
    candidates: tuple[str, ...]
    vocabulary: tuple[str, ...] = ()
    character_tags: tuple[tuple[str, tuple[str, ...]], ...] = ()
    vocabulary_statuses: tuple[tuple[str, str], ...] = ()
    vocabulary_readings: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class KanjiEntry:
    character: str
    on_readings: tuple[str, ...]
    kun_readings: tuple[str, ...]
    meanings: tuple[str, ...]
    stroke_count: int | None = None
    grade: int | None = None


@dataclass(frozen=True)
class ComponentEntry:
    key: str
    label: str
    svg: bytes
    prerequisites: tuple[str, ...] = ()


@dataclass(frozen=True)
class StrokeEntry:
    character: str
    svg: bytes
    components: tuple[str, ...]
    component_entries: tuple[ComponentEntry, ...] = ()
    prerequisites: tuple[str, ...] = ()


class KanjiProvider(Protocol):
    def lookup_kanji(self, character: str) -> KanjiEntry | None: ...


class StrokeProvider(Protocol):
    def lookup_strokes(self, character: str) -> StrokeEntry | None: ...


@dataclass(frozen=True)
class DiscoveryReport:
    scan: ScanResult
    entries: tuple[KanjiEntry, ...]
    strokes: tuple[StrokeEntry, ...]
    unmatched: tuple[str, ...]
    dictionary_loaded: bool
    provenance: tuple[str, ...]
    warnings: tuple[str, ...] = ()
    # Counts cover supported kanji recognition notes, not production mastery.
    existing_owned: int | None = None
    missing_owned: int | None = None
    attribution: tuple[str, ...] = ()
