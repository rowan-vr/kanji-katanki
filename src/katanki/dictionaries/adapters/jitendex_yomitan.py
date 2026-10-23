"""Bounded, offline Yomitan reader shared by builds, overrides and updates."""

import json
import math
import re
from functools import lru_cache
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from ...generation.discovery import extract_candidates

MAX_EXPANDED = 1024 * 1024 * 1024
MAX_BANK = 32 * 1024 * 1024


def nodes(value):
    if isinstance(value, list):
        for item in value:
            yield from nodes(item)
    elif isinstance(value, dict):
        yield value
        yield from nodes(value.get("content"))


def eligible(row):
    word, reading, tags, _, score, definitions, _, _ = row
    if not extract_candidates(word) or score < 100 or "★" not in tags:
        return False
    if any(tag in tags for tag in ("rarely", "obsolete", "old", "irregular")):
        return False
    return not any(
        node.get("data", {}).get("code") in {"uk", "arch", "obs", "rare"}
        for node in nodes(definitions)
    )


def _open(path):
    if Path(path).stat().st_size > 64 * 1024 * 1024:
        raise ValueError("Jitendex ZIP exceeds the 64 MiB input limit.")
    archive = ZipFile(path)
    infos = archive.infolist()
    names = [info.filename for info in infos]
    if (
        len(names) != len(set(names))
        or len(names) > 10000
        or sum(info.file_size for info in infos) > MAX_EXPANDED
    ):
        archive.close()
        raise ValueError("Duplicate files or excessive expanded Jitendex size.")
    return archive


def _index(archive):
    info = archive.getinfo("index.json")
    if info.file_size > 128 * 1024:
        raise ValueError("Jitendex index is too large.")
    index = json.loads(archive.read(info))
    if (
        not isinstance(index, dict)
        or index.get("format") != 3
        or not isinstance(index.get("revision"), str)
        or not index["revision"]
        or not isinstance(index.get("title"), str)
    ):
        raise ValueError("Expected a Yomitan format 3 dictionary with title and revision.")
    return index


def convert(source):
    """Retain valid spelling/reading pairs; never cross-join alternative forms."""
    try:
        with _open(source) as archive:
            index = _index(archive)
            words, count, banks = set(), 0, 0
            for name in sorted(archive.namelist()):
                if not re.fullmatch(r"term_bank_[0-9]+\.json", name):
                    continue
                banks += 1
                info = archive.getinfo(name)
                if info.file_size > MAX_BANK:
                    raise ValueError("Jitendex term bank is too large.")
                rows = json.loads(archive.read(info))
                if not isinstance(rows, list):
                    raise ValueError("Invalid Jitendex term bank.")
                for row in rows:
                    if (
                        not isinstance(row, list)
                        or len(row) != 8
                        or any(not isinstance(row[i], str) for i in (0, 1, 2, 3, 7))
                        or type(row[4]) not in (int, float)
                        or (isinstance(row[4], float) and not math.isfinite(row[4]))
                        or not isinstance(row[5], list)
                    ):
                        raise ValueError("Invalid Jitendex term row.")
                    count += 1
                    if eligible(row):
                        words.add((row[0], row[1], row[4]))
            if not banks or not count:
                raise ValueError("Jitendex contains no term entries.")
        data = {"format": 1, "version": index["revision"], "words": sorted(words)}
        index["term_count"] = count
        return (json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n").encode(), index
    except (BadZipFile, KeyError, TypeError, AttributeError, RecursionError) as error:
        raise ValueError("Invalid Jitendex Yomitan dictionary.") from error


@lru_cache(maxsize=4)
def _suggestions(path, size, modified):
    from ..words import WordSuggestions

    source = Path(path)
    payload, _ = convert(source)
    return WordSuggestions(json.loads(payload)["words"])


class JitendexYomitan:
    def __init__(self, source):
        self.source = Path(source)
        try:
            with _open(self.source) as archive:
                self.index = _index(archive)
        except (BadZipFile, KeyError, TypeError) as error:
            raise ValueError("Invalid Jitendex Yomitan dictionary.") from error
        self.version = self.index["revision"]
        self.attribution = f"{self.index['title']} ({self.version}); " + str(
            self.index.get("attribution", "Local Yomitan dictionary; see original notices.")
        )

    def lookup(self, character):
        stat = self.source.stat()
        return _suggestions(str(self.source.resolve()), stat.st_size, stat.st_mtime_ns).lookup(
            character
        )

    def lookup_words(self, character):
        return self.lookup(character)
