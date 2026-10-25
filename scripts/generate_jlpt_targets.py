"""Generate modern unofficial JLPT targets from checksum-pinned OpenJLPT files."""

import argparse
import json
import shutil
import sys
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from katanki.dictionaries.packs import revision  # noqa: E402
from katanki.stats.targets import MAX_BYTES, TargetGroup, TargetList, TargetSource  # noqa: E402

DATASET_ID = "jlpt-openjlpt"
TITLE = "JLPT N5–N1 (unofficial, OpenJLPT)"
ATTRIBUTION = (
    "OpenJLPT contributors; Jonathan Waller's community JLPT lists; "
    "KANJIDIC2 by James William Breen and EDRDG. "
    "Adaptation: kanji identities and modern level assignments only, grouped N5 to N1."
)


def generate(source: Path, output: Path, *, version: str, bundle: bool = False) -> TargetList:
    revision(version)
    lock_path = ROOT / "datasets/sources/jlpt-openjlpt.json"
    lock_bytes = lock_path.read_bytes()
    lock = json.loads(lock_bytes)
    groups = []
    seen = set()
    for level in range(5, 0, -1):
        name = f"n{level}.json"
        data = (source / name).read_bytes()
        if len(data) > MAX_BYTES or sha256(data).hexdigest() != lock["resources"][name]["sha256"]:
            raise ValueError(f"Missing or changed pinned OpenJLPT input: {name}.")
        entries = json.loads(data)
        if not isinstance(entries, list) or not entries:
            raise ValueError(f"Expected nonempty OpenJLPT level: {name}.")
        characters = []
        for entry in entries:
            if not isinstance(entry, dict) or entry.get("level") != f"N{level}":
                raise ValueError(f"Unexpected OpenJLPT level metadata in {name}.")
            character = entry.get("character")
            if not isinstance(character, str) or character in seen:
                raise ValueError(f"Missing or repeated OpenJLPT character in {name}.")
            characters.append(character)
            seen.add(character)
        # TargetGroup validates the shared exact Unicode identity policy.
        groups.append(TargetGroup(f"n{level}", f"N{level} (unofficial)", tuple(characters)))
    target = TargetList(
        DATASET_ID,
        TITLE,
        version,
        "jlpt-unofficial",
        TargetSource(
            "OpenJLPT modern JLPT classification (unofficial)",
            f"{lock['repository']}/tree/{lock['revision']}",
            lock["revision"],
            "CC BY-SA 4.0; https://creativecommons.org/licenses/by-sa/4.0/",
            ATTRIBUTION,
            "unofficial",
            sha256(lock_bytes).hexdigest(),
        ),
        tuple(groups),
    )
    payload = target.to_json().encode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)
    if bundle:
        dictionaries = ROOT / "src/katanki/dictionaries"
        original = json.loads((dictionaries / "manifests/joyo.json").read_text(encoding="utf-8"))
        notices = dictionaries / "bundled/licenses"
        notices.mkdir(parents=True, exist_ok=True)
        for name in ("LICENSE", "NOTICE.md"):
            data = (source / name).read_bytes()
            if sha256(data).hexdigest() != lock["resources"][name]["sha256"]:
                raise ValueError(f"Changed pinned OpenJLPT attribution: {name}.")
            (notices / f"OpenJLPT-{name}").write_bytes(data)
        (notices / "OpenJLPT-SOURCES.json").write_bytes(lock_bytes)
        raw = {
            "id": DATASET_ID,
            "name": TITLE,
            "format": "target_lists_json",
            "source": target.source.url,
            "capabilities": ["target_lists"],
            "compression": ["none"],
            "version": "Independent dated target-list release",
            "license": {
                "name": target.source.license,
                "url": "https://creativecommons.org/licenses/by-sa/4.0/",
                "attribution": ATTRIBUTION,
            },
            "default": True,
            "bundled": {
                "path": f"bundled/{DATASET_ID}.json",
                "sha256": sha256(payload).hexdigest(),
                "version": version,
                "entries": len(target.characters()),
                "license_files": [
                    *original["bundled"]["license_files"],
                    "bundled/licenses/OpenJLPT-LICENSE",
                    "bundled/licenses/OpenJLPT-NOTICE.md",
                    "bundled/licenses/OpenJLPT-SOURCES.json",
                ],
            },
        }
        (dictionaries / f"manifests/{DATASET_ID}.json").write_text(
            json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        destination = dictionaries / raw["bundled"]["path"]
        if output.resolve() != destination.resolve():
            shutil.copyfile(output, destination)
        candidate = ROOT / f"dist/targets/{DATASET_ID}.json"
        candidate.parent.mkdir(parents=True, exist_ok=True)
        if output.resolve() != candidate.resolve():
            shutil.copyfile(output, candidate)
        path = ROOT / "datasets/bundled-lock.json"
        build_lock = json.loads(path.read_text(encoding="utf-8"))
        build_lock["datasets"].pop(DATASET_ID, None)
        build_lock.setdefault("local_datasets", {})[DATASET_ID] = {
            "path": candidate.relative_to(ROOT).as_posix(),
            "sha256": sha256(payload).hexdigest(),
        }
        path.write_text(json.dumps(build_lock, indent=2) + "\n", encoding="utf-8")
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "data/upstream/openjlpt")
    parser.add_argument("--output", type=Path, default=ROOT / f"dist/targets/{DATASET_ID}.json")
    parser.add_argument("--version", required=True)
    parser.add_argument("--bundle", action="store_true")
    parser.add_argument(
        "--fetch", action="store_true", help="Fetch the exact checksum-pinned inputs"
    )
    args = parser.parse_args()
    if args.fetch:
        sys.path.insert(0, str(ROOT))
        from scripts.bundle_datasets import refresh_sources

        lock = json.loads((ROOT / "datasets/sources/jlpt-openjlpt.json").read_text())
        refresh_sources(lock, args.source, update_lock=False)
    target = generate(args.source, args.output, version=args.version, bundle=args.bundle)
    print(f"{target.title}: {len(target.characters())} unique kanji")
