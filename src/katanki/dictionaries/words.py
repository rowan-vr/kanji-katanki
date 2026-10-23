"""Small offline Jitendex word suggestions; never fetch data during review."""

from pathlib import Path

PACK = Path(__file__).with_name("bundled") / "jitendex.zip"
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


def selected_words(choices=()):
    from .adapters.jitendex_yomitan import JitendexYomitan
    from .preferences import dictionary_sources

    path = dictionary_sources(choices).get("jitendex")
    return JitendexYomitan(path) if path else WordSuggestions(())


def bundled_words():
    return selected_words()
