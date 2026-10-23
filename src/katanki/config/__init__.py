"""Versioned, collection-local preferences. Saving settings never approves generation."""

from dataclasses import asdict, dataclass

from ..common.models import ScanSelection

CONFIG_KEY = "katanki_settings"
VERSION = 5


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


GENERATION_CATEGORIES = ("recognition", "production", "parts")


@dataclass(frozen=True)
class GenerationSettings:
    auto_generate: bool = False
    target_deck_id: int | None = None
    default_tags: tuple[str, ...] = ()
    copy_source_tags: bool = False
    source_tag_patterns: tuple[str, ...] = ()

    def __post_init__(self):
        if type(self.auto_generate) is not bool or type(self.copy_source_tags) is not bool:
            raise ValueError("Generation switches must be enabled or disabled.")
        if self.target_deck_id is not None and (
            type(self.target_deck_id) is not int or self.target_deck_id <= 0
        ):
            raise ValueError("Select a valid target deck.")
        for values in (self.default_tags, self.source_tag_patterns):
            if not isinstance(values, tuple) or any(
                not isinstance(tag, str) or not tag or any(char.isspace() for char in tag)
                for tag in values
            ):
                raise ValueError("Tags and tag patterns must be nonempty, without spaces.")


@dataclass(frozen=True)
class CardSettings:
    show_examples: bool = True
    example_source: str = "discovered"
    furigana: bool = False
    auto_refresh: bool = True
    include_new: bool = True
    show_name: bool = True

    def __post_init__(self):
        if any(
            type(value) is not bool
            for value in (
                self.show_examples,
                self.furigana,
                self.auto_refresh,
                self.include_new,
                self.show_name,
            )
        ):
            raise ValueError("Card switches must be enabled or disabled.")
        if self.example_source not in ("discovered", "discovered_and_default"):
            raise ValueError("Choose discovered words or discovered and default words.")


@dataclass(frozen=True)
class DictionaryChoice:
    dataset_id: str
    mode: str = "bundled"
    path: str = ""

    def __post_init__(self):
        if not isinstance(self.dataset_id, str) or not self.dataset_id:
            raise ValueError("Choose a valid dictionary.")
        if self.mode not in ("bundled", "local", "disabled") or not isinstance(self.path, str):
            raise ValueError("Invalid dictionary source settings.")
        if self.mode == "local" and not self.path.strip():
            raise ValueError("Choose a local dictionary file or directory.")


@dataclass(frozen=True)
class Settings:
    sources: tuple[SourceRule, ...] = ()
    destination_deck_id: int | None = None
    include_primitives: bool = False
    generation: tuple[GenerationSettings, ...] = ()
    dictionaries: tuple[DictionaryChoice, ...] = ()
    cards: tuple[CardSettings, ...] = ()

    def __post_init__(self):
        if not self.generation:
            object.__setattr__(
                self,
                "generation",
                tuple(
                    GenerationSettings(
                        category in ("recognition", "production")
                        or (category == "parts" and self.include_primitives),
                        self.destination_deck_id,
                    )
                    for category in GENERATION_CATEGORIES
                ),
            )
        if len(self.generation) != 3 or any(
            not isinstance(item, GenerationSettings) for item in self.generation
        ):
            raise ValueError("Generation settings need Recognition, Production, and Parts.")

        if not self.cards:
            object.__setattr__(self, "cards", tuple(CardSettings() for _ in GENERATION_CATEGORIES))
        if len(self.cards) != len(GENERATION_CATEGORIES) or any(
            not isinstance(item, CardSettings) for item in self.cards
        ):
            raise ValueError("Card settings need Recognition, Production, and Parts.")

    def card_settings(self, category: str) -> CardSettings:
        return self.cards[GENERATION_CATEGORIES.index(category)]

    def generation_settings(self, category: str) -> GenerationSettings:
        return self.generation[GENERATION_CATEGORIES.index(category)]

    def to_dict(self) -> dict:
        sources = []
        for rule in self.sources:
            entry = asdict(rule)
            entry["deck_ids"] = list(rule.deck_ids)
            entry["fields"] = list(rule.fields)
            sources.append(entry)
        return {
            "version": VERSION,
            "dictionaries": [asdict(choice) for choice in self.dictionaries],
            "cards": {
                category: asdict(self.card_settings(category)) for category in GENERATION_CATEGORIES
            },
            "generation": {
                category: {
                    **asdict(self.generation_settings(category)),
                    "default_tags": list(self.generation_settings(category).default_tags),
                    "source_tag_patterns": list(
                        self.generation_settings(category).source_tag_patterns
                    ),
                }
                for category in GENERATION_CATEGORIES
            },
            "sources": sources,
            "destination_deck_id": self.destination_deck_id,
            "include_primitives": self.include_primitives,
        }


def from_dict(data) -> Settings:
    if data is None:
        return Settings()
    if not isinstance(data, dict) or type(data.get("version")) is not int:
        raise ValueError("Invalid Katanki settings format. Saved settings were preserved.")
    if data["version"] not in (1, 2, 3, 4, VERSION):
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
    generation = ()
    if data["version"] >= 3:
        profiles = data.get("generation", {})
        if not isinstance(profiles, dict):
            raise ValueError("Invalid generation settings.")
        settings = Settings(tuple(rules), destination, primitives)
        parsed = []
        for category in GENERATION_CATEGORIES:
            entry = profiles.get(category)
            if entry is None:
                parsed.append(settings.generation_settings(category))
                continue
            if not isinstance(entry, dict):
                raise ValueError("Invalid generation category settings.")
            tags, patterns = entry.get("default_tags", []), entry.get("source_tag_patterns", [])
            if not isinstance(tags, list) or not isinstance(patterns, list):
                raise ValueError("Invalid saved tags or tag patterns.")
            parsed.append(
                GenerationSettings(
                    entry.get(
                        "auto_generate", settings.generation_settings(category).auto_generate
                    ),
                    entry.get("target_deck_id"),
                    tuple(tags),
                    entry.get("copy_source_tags", False),
                    tuple(patterns),
                )
            )
        generation = tuple(parsed)
    entries = data.get("dictionaries", []) if data["version"] >= 4 else []
    if not isinstance(entries, list):
        raise ValueError("Invalid saved dictionary choices.")
    dictionaries = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Invalid saved dictionary choice.")
        dictionaries.append(
            DictionaryChoice(
                entry.get("dataset_id"), entry.get("mode", "bundled"), entry.get("path", "")
            )
        )
    if len({choice.dataset_id for choice in dictionaries}) != len(dictionaries):
        raise ValueError("Duplicate dictionary choices.")
    cards = ()
    if data["version"] >= 5:
        profiles = data.get("cards", {})
        if not isinstance(profiles, dict):
            raise ValueError("Invalid card settings.")
        parsed = []
        for category in GENERATION_CATEGORIES:
            entry = profiles.get(category, {})
            if not isinstance(entry, dict):
                raise ValueError("Invalid card category settings.")
            parsed.append(
                CardSettings(
                    entry.get("show_examples", True),
                    entry.get("example_source", "discovered"),
                    entry.get("furigana", False),
                    entry.get("auto_refresh", True),
                    entry.get("include_new", True),
                    entry.get("show_name", True),
                )
            )
        cards = tuple(parsed)
    return Settings(tuple(rules), destination, primitives, generation, tuple(dictionaries), cards)


def load_settings(collection) -> Settings:
    return from_dict(collection.get_config(CONFIG_KEY, None))


def save_settings(collection, settings: Settings) -> None:
    data = settings.to_dict()
    from_dict(data)
    collection.set_config(CONFIG_KEY, data)
