"""KANJIDIC2 XML to normalized kanji data; no provider-specific downstream access."""

from pathlib import Path

from ...common.models import KanjiEntry
from .xml_data import read_xml


class KanjidicXml:
    def __init__(self, path: Path):
        root, self.source_bytes = read_xml(path)
        if root.tag != "kanjidic2":
            raise ValueError("Expected a KANJIDIC2 XML root.")
        self.version = root.findtext("header/date_of_creation") or "unknown date"
        self.entries = {}
        for node in root.findall("character"):
            character = node.findtext("literal", "")
            if len(character) != 1 or character in self.entries:
                raise ValueError("Invalid or duplicate KANJIDIC2 character.")

            def readings(kind, node=node):
                return tuple(
                    dict.fromkeys(
                        item.text
                        for item in node.findall("reading_meaning/rmgroup/reading")
                        if item.get("r_type") == kind and item.text
                    )
                )

            meanings = tuple(
                dict.fromkeys(
                    item.text
                    for item in node.findall("reading_meaning/rmgroup/meaning")
                    if item.get("m_lang", "en") == "en" and item.text
                )
            )
            stroke = node.findtext("misc/stroke_count")
            grade = node.findtext("misc/grade")
            self.entries[character] = KanjiEntry(
                character,
                readings("ja_on"),
                readings("ja_kun"),
                meanings,
                int(stroke) if stroke else None,
                int(grade) if grade else None,
            )
        if not self.entries:
            raise ValueError("KANJIDIC2 contains no character entries.")

    def lookup_kanji(self, character: str) -> KanjiEntry | None:
        return self.entries.get(character)
