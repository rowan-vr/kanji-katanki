"""Only the contracts needed for read-only discovery and local dictionaries."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ScanSelection:
    deck_ids: tuple[int, ...]
    note_type_id: int
    fields: tuple[str, ...]

    def __post_init__(self):
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


@dataclass(frozen=True)
class ScanResult:
    scanned_notes: int
    candidates: tuple[str, ...]


@dataclass(frozen=True)
class KanjiEntry:
    character: str
    on_readings: tuple[str, ...]
    kun_readings: tuple[str, ...]
    meanings: tuple[str, ...]
    stroke_count: int | None = None
    grade: int | None = None


@dataclass(frozen=True)
class StrokeEntry:
    character: str
    svg: bytes
    components: tuple[str, ...]


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
    # Existing/missing owned notes cannot be measured until Phase 2 identities exist.
    existing_owned: int | None = None
    missing_owned: int | None = None
