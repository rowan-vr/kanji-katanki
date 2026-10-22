"""Extract candidate ideographs; dictionary membership determines support."""

import re
import unicodedata
from collections.abc import Iterable
from html.parser import HTMLParser

from ...common.models import NoteText, ScanResult


class _VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden.append(tag)

    def handle_endtag(self, tag):
        if self.hidden and self.hidden[-1] == tag:
            self.hidden.pop()

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def extract_candidates(text: str) -> set[str]:
    parser = _VisibleText()
    parser.feed(re.sub(r"\[sound:[^\]]*\]", "", text, flags=re.IGNORECASE))
    parser.close()
    # Do not NFKC-normalize: compatibility ideographs can have distinct identities.
    return {
        character
        for character in "".join(parser.parts)
        if unicodedata.name(character, "").startswith(
            ("CJK UNIFIED IDEOGRAPH-", "CJK COMPATIBILITY IDEOGRAPH-")
        )
        or character == "〇"
    }


def scan_notes(notes: Iterable[NoteText]) -> ScanResult:
    candidates: set[str] = set()
    count = 0
    for note in notes:
        count += 1
        for field in note.fields:
            candidates.update(extract_candidates(field))
    return ScanResult(count, tuple(sorted(candidates)))
