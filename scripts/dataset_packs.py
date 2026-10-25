"""Prepare versioned release assets, or restore exact locked packs for add-on builds."""

import argparse
import json
import re
import shutil
import sys
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from katanki.dictionaries.downloads import download  # noqa: E402
from katanki.dictionaries.packs import (  # noqa: E402
    RELEASE_PREFIX,
    read_catalog,
    revision,
    unpack,
    validate_contents,
    verify_download,
)
from katanki.dictionaries.registry import list_datasets  # noqa: E402

BUNDLED = ROOT / "src" / "katanki" / "dictionaries" / "bundled"
CACHE = ROOT / "data" / "packs"
LOCK = ROOT / "datasets" / "bundled-lock.json"


def prepare(tag: str, output: Path, *, refresh: bool = False) -> dict:
    if not re.fullmatch(r"datasets-[A-Za-z0-9._-]+", tag):
        raise ValueError("Use a datasets- release tag with no slashes or whitespace.")
    from scripts.build_addon import verify_bundled_assets
    from scripts.bundle_datasets import prepare_from_sources

    if refresh:
        prepare_from_sources(refresh=True)
    else:
        try:
            verify_bundled_assets(ROOT / "src" / "katanki")
        except (OSError, ValueError):
            prepare_from_sources(offline=True)
    verify_bundled_assets(ROOT / "src" / "katanki")
    output.mkdir(parents=True, exist_ok=True)
    catalog = {"schema_version": 1, "datasets": {}}
    for manifest in list_datasets():
        bundle = manifest.bundled
        if bundle["entries"] < 6000 and manifest.format != "target_lists_json":
            raise ValueError(f"Unexpectedly small {manifest.name}; review upstream coverage.")
        filename = f"{manifest.id}.zip"
        files = {
            name: (BUNDLED.parent / name).read_bytes()
            for name in sorted({bundle["path"], *bundle["license_files"]})
        }
        metadata = {
            "id": manifest.id,
            "format_version": 1,
            "revision": revision(bundle["version"]),
            "bundled": bundle,
            "files": {name: sha256(data).hexdigest() for name, data in files.items()},
        }
        files["PACK.json"] = (json.dumps(metadata, indent=2) + "\n").encode("utf-8")
        path = output / filename
        with ZipFile(path, "w") as archive:
            for name, payload in sorted(files.items()):
                info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = 0o644 << 16
                info.compress_type = ZIP_STORED if name == "bundled/jitendex.zip" else ZIP_DEFLATED
                archive.writestr(info, payload)
        data = path.read_bytes()
        entry = {
            "version": bundle["version"],
            "revision": metadata["revision"],
            "format_version": 1,
            "url": RELEASE_PREFIX + tag.removeprefix("datasets-") + "/" + filename,
            "sha256": sha256(data).hexdigest(),
            "bytes": len(data),
        }
        # Round-trip every candidate using the same validator as installed add-ons.
        with TemporaryDirectory() as directory:
            unpack(data, manifest.id, entry, Path(directory))
        catalog["datasets"][manifest.id] = entry
        CACHE.mkdir(parents=True, exist_ok=True)
        (CACHE / f"{entry['sha256']}.zip").write_bytes(data)
    read_catalog(catalog)
    (output / "catalog.json").write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    review = output / "review"
    review.mkdir(exist_ok=True)
    shutil.copyfile(BUNDLED / "SOURCES.json", review / "SOURCES.json")
    for manifest in list_datasets():
        shutil.copyfile(
            BUNDLED.parent / "manifests" / f"{manifest.id}.json", review / f"{manifest.id}.json"
        )
    return catalog


def restore(*, offline: bool = False) -> None:
    raw = json.loads(LOCK.read_text(encoding="utf-8"))
    catalog = read_catalog(raw)
    manifests = [manifest for manifest in list_datasets() if manifest.default]
    local = raw.get("local_datasets", {})
    if not isinstance(local, dict) or set(local) & set(catalog):
        raise ValueError("Invalid or conflicting local dataset baselines.")
    if set(catalog) | set(local) != {manifest.id for manifest in manifests}:
        raise ValueError("Build lock must specify every default dictionary in a supported format.")
    CACHE.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=BUNDLED.parent, prefix=".restore-") as directory:
        stage = Path(directory) / "dictionaries"
        for manifest in manifests:
            if manifest.id in local:
                continue  # Restore reviewed local JSON after shared license files.
            release = catalog[manifest.id]
            path = CACHE / f"{release['sha256']}.zip"
            data = path.read_bytes() if path.is_file() else None
            if data is not None:
                try:
                    verify_download(data, release)
                except ValueError:
                    data = None
            if data is None:
                if offline:
                    raise ValueError(
                        f"Verified pack missing for {manifest.name}; build online first."
                    )
                data = download(release["url"], limit=release["bytes"])
                verify_download(data, release)
                temporary = None
                try:
                    # The cache may be on a different filesystem from the
                    # package staging directory. Rename within the cache only.
                    with NamedTemporaryFile(dir=CACHE, prefix=".download-", delete=False) as stream:
                        temporary = Path(stream.name)
                        stream.write(data)
                    temporary.replace(path)
                finally:
                    if temporary is not None:
                        temporary.unlink(missing_ok=True)
            pack_stage = Path(directory) / manifest.id
            pack_stage.mkdir()
            metadata = unpack(data, manifest.id, release, pack_stage)
            if metadata["bundled"] != manifest.bundled:
                raise ValueError(f"Locked {manifest.name} pack differs from its manifest.")
            # Shared attribution/source files must agree between the two packs.
            for name in metadata["files"]:
                source, target = pack_stage / name, stage / name
                if name == "bundled/SOURCES.json" and (BUNDLED / "SOURCES.json").is_file():
                    if json.loads(source.read_text(encoding="utf-8")) != json.loads(
                        (BUNDLED / "SOURCES.json").read_text(encoding="utf-8")
                    ):
                        raise ValueError("Locked packs differ from tracked source provenance.")
                if target.exists() and target.read_bytes() != source.read_bytes():
                    raise ValueError(f"Locked packs contain conflicting shared file: {name}")
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        for manifest in manifests:
            if manifest.id not in local:
                continue
            entry = local[manifest.id]
            if (
                manifest.format != "target_lists_json"
                or manifest.bundled is None
                or not isinstance(entry, dict)
                or set(entry) != {"path", "sha256"}
                or entry["path"] != f"dist/targets/{manifest.id}.json"
                or entry["sha256"] != manifest.bundled["sha256"]
            ):
                raise ValueError("Invalid local target dataset baseline.")
            payload = (ROOT / entry["path"]).read_bytes()
            if sha256(payload).hexdigest() != entry["sha256"]:
                raise ValueError("Local target dataset checksum mismatch.")
            target = stage / manifest.bundled["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            validate_contents(manifest.id, stage, manifest.bundled)
            if any(not (stage / name).is_file() for name in manifest.bundled["license_files"]):
                raise ValueError("Local target dataset notices are missing.")
        previous = Path(directory) / "previous"
        if BUNDLED.exists():
            BUNDLED.rename(previous)
        try:
            (stage / "bundled").rename(BUNDLED)
        except BaseException:
            if previous.exists():
                previous.rename(BUNDLED)
            raise
    print("Restored checksum-locked dictionary packs.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tag", required=True, help="New, never previously published datasets- tag"
    )
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "datasets")
    parser.add_argument(
        "--refresh", action="store_true", help="Fetch current official upstream data"
    )
    args = parser.parse_args()
    # Invoking scripts directly does not put the repository root on sys.path.
    sys.path.insert(0, str(ROOT))
    prepare(args.tag, args.output, refresh=args.refresh)
