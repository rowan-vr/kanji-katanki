"""Bundle the full pinned Jitendex export and a lightweight offline suggestion index."""

import argparse
import json
import shutil
import sys
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from katanki.generation.discovery import extract_candidates  # noqa: E402

LOCK = ROOT / "datasets" / "jitendex-lock.json"
TARGET = ROOT / "src/katanki/dictionaries/word_pack"


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
    # Conservative: skip any entry with kana-preferred/archaic senses. Yomitan
    # rows already express valid spelling/reading pairs; never cross-join forms.
    return not any(
        node.get("data", {}).get("code") in {"uk", "arch", "obs", "rare"}
        for node in nodes(definitions)
    )


def convert(source):
    with ZipFile(source) as archive:
        if sum(info.file_size for info in archive.infolist()) > 1024 * 1024 * 1024:
            raise ValueError("Jitendex expanded size exceeds limit.")
        index = json.loads(archive.read("index.json"))
        if index["format"] != 3:
            raise ValueError("Expected Yomitan format 3.")
        words = set()
        for name in sorted(archive.namelist()):
            if name.startswith("term_bank_") and name.endswith(".json"):
                for row in json.loads(archive.read(name)):
                    if eligible(row):
                        words.add((row[0], row[1], row[4]))
    data = {"format": 1, "version": index["revision"], "words": sorted(words)}
    return (json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n").encode(), index


def prepare(*, offline=False):
    from scripts.bundle_datasets import refresh_sources

    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    TARGET.mkdir(parents=True, exist_ok=True)
    expected = lock["pack_sha256"]
    output = TARGET / "words.json"
    if output.is_file() and sha256(output.read_bytes()).hexdigest() == expected:
        if (
            (TARGET / "SOURCES.json").is_file()
            and (TARGET / "SOURCES.json").read_bytes() == LOCK.read_bytes()
            and (TARGET / "NOTICE.txt").is_file()
            and (TARGET / "NOTICE.txt").read_text(encoding="utf-8") == lock["notice"] + "\n"
            and all(
                (TARGET / name).is_file()
                and sha256((TARGET / name).read_bytes()).hexdigest() == resource["sha256"]
                for name, resource in lock["resources"].items()
            )
        ):
            return
    cache = ROOT / "data/upstream"
    if not offline:
        refresh_sources(lock, cache, update_lock=False)
    for name, resource in lock["resources"].items():
        if sha256((cache / name).read_bytes()).hexdigest() != resource["sha256"]:
            raise ValueError(f"Missing or changed Jitendex source: {name}")
    payload, index = convert(cache / "jitendex-yomitan.zip")
    if sha256(payload).hexdigest() != expected or index["revision"] != lock["version"]:
        raise ValueError("Jitendex conversion differs from locked pack.")
    (TARGET / "NOTICE.txt").write_text(lock["notice"] + "\n", encoding="utf-8")
    for name in lock["resources"]:
        shutil.copyfile(cache / name, TARGET / name)
    (TARGET / "SOURCES.json").write_bytes(LOCK.read_bytes())
    output.write_bytes(payload)


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    prepare(offline=parser.parse_args().offline)
