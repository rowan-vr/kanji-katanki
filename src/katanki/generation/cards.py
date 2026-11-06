"""Offline card definitions and escaped content, independent of Anki/Qt."""

import re
import unicodedata
from dataclasses import dataclass
from html import escape, unescape

from ..common.models import WORD_STATUS_ORDER
from .card_layout import BACK, PARTS_FRONT, PRODUCTION_FRONT, RECOGNITION_FRONT, WORD_LEGEND
from .card_layout import CSS as CSS
from .examples import STATE_FIELD, encode_state, managed_fields
from .planner import NOTE_TYPES, Identity


@dataclass(frozen=True)
class NoteTypeSpec:
    key: str
    name: str
    fields: tuple[str, ...]
    front: str
    back: str


def note_type_spec(key: str) -> NoteTypeSpec:
    if key not in NOTE_TYPES:
        raise ValueError("Unknown Katanki note type.")
    kind, mode = key.split("-")
    field = "Character" if kind == "kanji" else "Component"
    front = PARTS_FRONT if kind == "primitive" else RECOGNITION_FRONT
    if mode == "production":
        front = PRODUCTION_FRONT
    label = ("Kanji" if kind == "kanji" else "Parts") + " · " + mode.title()
    front = front.replace("{{CardLabel}}", label)
    back = (
        BACK.replace("{{CardLabel}}", label)
        .replace("{{WordsLabel}}", "Words" if kind == "kanji" else "Related kanji")
        .replace("{{CardKind}}", kind)
        .replace("{{WordLegend}}", WORD_LEGEND if kind == "kanji" else "")
    )
    return NoteTypeSpec(
        key,
        "Kanji Katanki — " + kind.title() + " " + mode.title(),
        (
            field,
            "Display",
            "Prompt",
            "Meanings",
            "Readings",
            "Components",
            "Strokes",
            "Attribution",
            "VocabExamples",
            "ExampleLimit",
            STATE_FIELD,
        ),
        front,
        back,
    )


@dataclass(frozen=True)
class CardContent:
    identity: Identity
    display: str
    meanings: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()
    components: tuple[str, ...] = ()
    svg: bytes = b""
    prompt: str = ""
    attribution: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()
    example_limit: int = 5
    show_examples: bool = True
    discovered_examples: tuple[str, ...] = ()
    example_statuses: tuple[tuple[str, str], ...] = ()
    front_examples: tuple[str, ...] | None = None
    back_examples: tuple[str, ...] | None = None

    example_readings: tuple[tuple[str, str], ...] = ()
    front_furigana: bool | None = None
    back_furigana: bool = True

    example_meanings: tuple[tuple[str, tuple[str, ...]], ...] = ()

    # (component, meaning, your kanji using it, other dictionary kanji using it);
    # each kanji is a (character, meaning) pair.
    component_details: tuple[tuple, ...] = ()

    def fields(self) -> dict[str, str]:
        spec = note_type_spec(self.identity.note_type)
        statuses = dict(self.example_statuses)
        readings = dict(self.example_readings)
        meanings = dict(self.example_meanings)
        front = set(self.front_examples) if self.front_examples is not None else set(self.examples)
        back = set(self.back_examples) if self.back_examples is not None else set(self.examples)
        values = {
            spec.fields[0]: self.identity.key,
            "Display": escape(self.display),
            "ExampleLimit": str(self.example_limit if self.show_examples else -1),
            "VocabExamples": "".join(
                '<div data-front="'
                + ("true" if word in front else "false")
                + '" data-back="'
                + ("true" if word in back else "false")
                + '" data-source="'
                + (
                    "components"
                    if self.identity.kind == "primitive"
                    else "vocabulary"
                    if word in self.discovered_examples
                    else "default"
                )
                + '" data-reading="'
                + escape(readings.get(word, ""), quote=True)
                + '" data-meaning="'
                + escape("\n".join(meanings.get(word, ())), quote=True)
                + '" data-front-furigana="'
                + str(
                    self.front_furigana
                    if self.front_furigana is not None
                    else self.identity.note_type == "kanji-production"
                ).lower()
                + '" data-back-furigana="'
                + str(self.back_furigana).lower()
                + '" data-masked="'
                + escape(word.replace(self.identity.key, "__"), quote=True)
                + '" data-status="'
                + (statuses.get(word) if statuses.get(word) in WORD_STATUS_ORDER else "missing")
                + '">'
                + escape(word)
                + "</div>"
                for word in self.examples
            ),
            "Prompt": "<br>".join(escape(line) for line in self.prompt.split("\n")),
            "Meanings": escape(", ".join(self.meanings)),
            "Readings": escape(", ".join(self.readings)),
            "Components": components_html(self.components, self.component_details),
            "Strokes": self.svg.decode("utf-8") if self.svg else "Stroke data unavailable",
            "Attribution": "<br>".join(dict.fromkeys(escape(line) for line in self.attribution)),
        }
        values[STATE_FIELD] = encode_state(managed_fields(values, self.identity))
        return values


def components_html(components, details) -> str:
    """Comma-separated components; detail spans stay readable in custom templates."""
    if not components:
        return "none listed"
    if not details:
        return escape(", ".join(components))
    known = {detail[0]: detail[1:] for detail in details}

    def rows(kanji):
        return escape("\n".join(c + "\t" + m for c, m in kanji), quote=True)

    parts = []
    for key in components:
        if key not in known:
            parts.append(escape(key))
            continue
        meaning, kanji, *more = known[key]
        more = more[0] if more else ()
        parts.append(
            '<span data-meaning="'
            + escape(meaning, quote=True)
            + '" data-kanji="'
            + rows(kanji)
            + ('" data-more="' + rows(more) if more else "")
            + '">'
            + escape(key)
            + "</span>"
        )
    return ", ".join(parts)


def component_keys(html: str) -> tuple[str, ...]:
    """Read the visible component list from plain or detailed Components content."""
    text = unescape(re.sub(r"<[^>]*>", "", html)).strip()
    if text == "none listed":
        return ()
    return tuple(part.strip() for part in text.split(",") if part.strip())


def normalize_prompt(text: str) -> str:
    return unicodedata.normalize("NFC", " ".join(text.split())).casefold()


def vocabulary_prompt(character: str, meanings: tuple[str, ...], vocabulary: tuple[str, ...]):
    """Copy only matching source words and blank every occurrence of the target."""
    examples = tuple(sorted({word for word in vocabulary if character in word}))
    masked = tuple(word.replace(character, "__") for word in examples)
    prompt = "\n".join((", ".join(meanings), "", *masked)) if examples else ""
    return prompt, examples
