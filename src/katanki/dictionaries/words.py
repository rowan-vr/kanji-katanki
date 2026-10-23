"""Small offline Jitendex word suggestions; never fetch data during review."""

import json
from functools import lru_cache
from pathlib import Path

PACK = Path(__file__).with_name("word_pack") / "words.json"
ATTRIBUTION = (
    "Jitendex © Stephen Kraus, CC BY-SA 4.0; JMdict © EDRDG. "
    "Word selection adapted by Kanji Katanki. https://jitendex.org/pages/legal.html"
)


class WordSuggestions:
    def __init__(self, rows):
        self.by_character = {}
        for word, reading, _score in sorted(rows, key=lambda row: (-row[2], len(row[0]), *row[:2])):
            for character in set(word):
                self.by_character.setdefault(character, []).append((word, reading))

    def lookup(self, character):
        """Rank by upstream priority, then length/spelling; keep one reading per word."""
        return tuple(dict.fromkeys(word for word, _ in self.by_character.get(character, ())))


@lru_cache(maxsize=1)
def bundled_words():
    if not PACK.is_file():
        return WordSuggestions(())
    data = json.loads(PACK.read_text(encoding="utf-8"))
    if data["format"] != 1:
        raise ValueError("Unsupported word pack format.")
    return WordSuggestions(data["words"])
