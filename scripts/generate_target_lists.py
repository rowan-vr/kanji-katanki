"""Generate an independent canonical target dataset from a KANJIDIC2 snapshot."""

import argparse
import json
import shutil
import sys
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from katanki.dictionaries.adapters.kanjidic2_xml import KanjidicXml  # noqa: E402
from katanki.dictionaries.packs import revision  # noqa: E402
from katanki.dictionaries.registry import DatasetManifest, read_manifest  # noqa: E402
from katanki.stats.targets import TargetGroup, TargetList, TargetSource  # noqa: E402

DATASET_IDS = ("school-grades", "joyo")


def target_source(provider: KanjidicXml, manifest: DatasetManifest) -> TargetSource:
    return TargetSource(
        manifest.name,
        manifest.source,
        provider.version,
        manifest.license_name,
        manifest.attribution,
        "unofficial",
        sha256(provider.source_bytes).hexdigest(),
    )


def school_grades(provider: KanjidicXml, manifest: DatasetManifest, version: str) -> TargetList:
    groups = tuple(
        TargetGroup(
            f"grade-{grade}",
            f"Elementary grade {grade}",
            tuple(sorted(char for char, entry in provider.entries.items() if entry.grade == grade)),
        )
        for grade in (1, 2, 3, 4, 5, 6)
    )
    return TargetList(
        "school-grades",
        "School grades (Kyōiku kanji)",
        version,
        "school-grades",
        target_source(provider, manifest),
        groups,
    )


def joyo(provider: KanjidicXml, manifest: DatasetManifest, version: str) -> TargetList:
    # Grades 1–6 are the elementary subset; grade 8 is the remaining Jōyō.
    characters = tuple(
        sorted(
            char for char, entry in provider.entries.items() if entry.grade in (1, 2, 3, 4, 5, 6, 8)
        )
    )
    return TargetList(
        "joyo",
        "Jōyō kanji",
        version,
        "joyo",
        target_source(provider, manifest),
        (TargetGroup("all", "All Jōyō kanji", characters),),
    )


def generate(
    source: Path,
    output: Path,
    *,
    version: str,
    bundle: bool = False,
    dataset_id: str = "school-grades",
) -> TargetList:
    """Generation is explicit; normal builds copy the reviewed, pinned JSON bytes."""
    revision(version)
    dictionaries = ROOT / "src/katanki/dictionaries"
    manifest_path = dictionaries / "manifests/kanjidic2.json"
    source_manifest = read_manifest(manifest_path)
    builders = {"school-grades": school_grades, "joyo": joyo}
    if dataset_id not in builders:
        raise ValueError("Unknown target dataset generator.")
    target = builders[dataset_id](KanjidicXml(source), source_manifest, version)
    payload = target.to_json().encode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)
    if bundle:
        # Keep unpublished candidates in ignored build output until release promotion.
        candidate = ROOT / f"dist/targets/{dataset_id}.json"
        candidate.parent.mkdir(parents=True, exist_ok=True)
        if output.resolve() != candidate.resolve():
            candidate.write_bytes(payload)
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        raw.update(
            id=dataset_id,
            name=target.title,
            format="target_lists_json",
            capabilities=["target_lists"],
            compression=["none"],
            version="Independent dated target-list release",
        )
        raw["bundled"] = dict(
            source_manifest.bundled,
            path=f"bundled/{dataset_id}.json",
            version=version,
            entries=len(target.characters()),
            sha256=sha256(payload).hexdigest(),
        )
        (dictionaries / f"manifests/{dataset_id}.json").write_text(
            json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        destination = dictionaries / raw["bundled"]["path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        if output.resolve() != destination.resolve():
            shutil.copyfile(output, destination)
        lock_path = ROOT / "datasets/bundled-lock.json"
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        lock["datasets"].pop(dataset_id, None)
        lock.setdefault("local_datasets", {})[dataset_id] = {
            "path": candidate.relative_to(ROOT).as_posix(),
            "sha256": sha256(payload).hexdigest(),
        }
        lock_path.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, default=ROOT / "src/katanki/dictionaries/bundled/kanjidic2.xml"
    )
    parser.add_argument("--dataset", choices=(*DATASET_IDS, "all"), default="all")
    parser.add_argument("--output", type=Path, help="Output JSON for a single selected dataset")
    parser.add_argument(
        "--version", required=True, help="Independent target release date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--bundle",
        action="store_true",
        help="Update generated candidate, manifest and local build lock",
    )
    args = parser.parse_args()
    if args.dataset == "all" and args.output is not None:
        parser.error("Choose a single --dataset when using --output.")
    for dataset_id in DATASET_IDS if args.dataset == "all" else (args.dataset,):
        output = args.output or ROOT / f"dist/targets/{dataset_id}.json"
        result = generate(
            args.source,
            output,
            version=args.version,
            bundle=args.bundle,
            dataset_id=dataset_id,
        )
        print(f"{result.id} {result.version}: {len(result.characters())} unique targets → {output}")
