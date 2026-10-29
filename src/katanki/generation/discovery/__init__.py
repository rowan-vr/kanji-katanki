"""Extract candidate ideographs; dictionary membership determines support."""

import re
import unicodedata
from collections.abc import Iterable
from html.parser import HTMLParser

from ...common.characters import is_kanji
from ...common.models import WORD_STATUS_ORDER, NoteText, ScanResult


class _VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "rt", "rp"}:
            self.hidden.append(tag)
        elif tag in {"br", "div", "p", "li"} and not self.hidden:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if self.hidden and self.hidden[-1] == tag:
            self.hidden.pop()
        elif tag in {"div", "p", "li"} and not self.hidden:
            self.parts.append(" ")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def visible_text(text: str) -> str:
    parser = _VisibleText()
    parser.feed(re.sub(r"\[sound:[^\]]*\]", "", text, flags=re.IGNORECASE))
    parser.close()
    return "".join(parser.parts)


def extract_candidates(text: str) -> set[str]:
    # Do not NFKC-normalize: compatibility ideographs can have distinct identities.
    return {character for character in visible_text(text) if is_kanji(character)}


def extract_vocabulary(text: str) -> set[str]:
    """Selected expression fields supply examples; no dictionary word guessing.

    Retain Japanese word runs, including okurigana, and discard media, markup,
    furigana annotations and non-Japanese separators. Ruby readings are hidden
    by visible_text(). Source notes/IDs are never retained.
    """
    text = re.sub(r"\[[^]\n]*\]", "", visible_text(text))
    words = set()
    current = []
    for character in (*text, " "):
        name = unicodedata.name(character, "")
        japanese = (
            name.startswith(
                ("CJK UNIFIED IDEOGRAPH-", "CJK COMPATIBILITY IDEOGRAPH-", "HIRAGANA", "KATAKANA")
            )
            or character in "々〆〇ー"
        )
        if japanese:
            current.append(character)
        elif current:
            word = "".join(current)
            if extract_candidates(word):
                words.add(word)
            current.clear()
    return words


def scan_notes(notes: Iterable[NoteText]) -> ScanResult:
    candidates: set[str] = set()
    vocabulary: set[str] = set()
    tags_by_character = {}
    statuses = {}
    readings = {}
    count = 0
    for note in notes:
        count += 1
        for index, field in enumerate(note.fields):
            characters = extract_candidates(field)
            candidates.update(characters)
            for character in characters:
                tags_by_character.setdefault(character, set()).update(note.tags)
            words = extract_vocabulary(field)
            vocabulary.update(words)
            # A separate reading describes a single expression, not a sentence/list.
            if len(words) == 1 and index < len(note.field_readings):
                reading = visible_text(note.field_readings[index]).strip()
                if reading:
                    readings.setdefault(next(iter(words)), reading)
            for word in words:
                status = note.word_status
                if WORD_STATUS_ORDER.get(status, 4) < WORD_STATUS_ORDER.get(statuses.get(word), 4):
                    statuses[word] = status
    return ScanResult(
        count,
        tuple(sorted(candidates)),
        tuple(sorted(vocabulary)),
        tuple(
            (key, tuple(sorted(tags))) for key, tags in sorted(tags_by_character.items()) if tags
        ),
        tuple(sorted(statuses.items())),
        tuple(sorted(readings.items())),
    )
