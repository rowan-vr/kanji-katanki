"""Versioned, collection-local preferences. Saving settings never approves generation."""

from dataclasses import asdict, dataclass

from ..common.models import ScanSelection

CONFIG_KEY = "katanki_settings"
VERSION = 2


@dataclass(frozen=True)
class SourceRule:
    deck_pattern: str
    note_type_id: int
    fields: tuple[str, ...]
    # Preserve stable IDs from version 1 and explicit deck choices, including renames.
    deck_ids: tuple[int, ...] = ()

    def __post_init__(self):
        if not isinstance(self.deck_pattern, str) or (
            not self.deck_pattern.strip() and not self.deck_ids
        ):
            raise ValueError("Enter a deck name or pattern (* for all decks).")
        ScanSelection(self.deck_ids or (1,), self.note_type_id, self.fields)


@dataclass(frozen=True)
class Settings:
    sources: tuple[SourceRule, ...] = ()
    destination_deck_id: int | None = None
    include_primitives: bool = False

    def to_dict(self) -> dict:
        sources = []
        for rule in self.sources:
            entry = asdict(rule)
            entry["deck_ids"] = list(rule.deck_ids)
            entry["fields"] = list(rule.fields)
            sources.append(entry)
        return {
            "version": VERSION,
            "sources": sources,
            "destination_deck_id": self.destination_deck_id,
            "include_primitives": self.include_primitives,
        }


def from_dict(data) -> Settings:
    if data is None:
        return Settings()
    if not isinstance(data, dict) or type(data.get("version")) is not int:
        raise ValueError("Invalid Katanki settings format. Saved settings were preserved.")
    if data["version"] not in (1, VERSION):
        raise ValueError("Unsupported Katanki settings version. Saved settings were preserved.")
    if data["version"] == 1:
        legacy = data.get("source")
        entries = [] if legacy is None else [legacy]
    else:
        entries = data.get("sources", [])
    if not isinstance(entries, list):
        raise ValueError("Invalid saved vocabulary sources.")
    rules = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Invalid saved vocabulary source.")
        decks, fields = entry.get("deck_ids", []), entry.get("fields")
        if not isinstance(decks, list) or not isinstance(fields, list):
            raise ValueError("Invalid saved vocabulary decks or fields.")
        rules.append(
            SourceRule(
                entry.get("deck_pattern", ""),
                entry.get("note_type_id"),
                tuple(fields),
                tuple(decks),
            )
        )
    destination = data.get("destination_deck_id")
    if destination is not None and (type(destination) is not int or destination <= 0):
        raise ValueError("Invalid saved destination deck.")
    primitives = data.get("include_primitives", False)
    if type(primitives) is not bool:
        raise ValueError("Invalid saved component preference.")
    return Settings(tuple(rules), destination, primitives)


def load_settings(collection) -> Settings:
    return from_dict(collection.get_config(CONFIG_KEY, None))


def save_settings(collection, settings: Settings) -> None:
    data = settings.to_dict()
    from_dict(data)
    collection.set_config(CONFIG_KEY, data)
