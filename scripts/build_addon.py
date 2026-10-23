"""Build a self-contained add-on, with __init__.py at the archive root."""

import argparse
import json
import subprocess
import sys
from hashlib import sha256
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

ROOT = Path(__file__).resolve().parents[1]


def verify_bundled_assets(source: Path) -> None:
    """Fail packaging if defaults/notices are missing or have drifted from their lock."""
    dictionaries = source / "dictionaries"
    for manifest_file in sorted((dictionaries / "manifests").glob("*.json")):
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        if not manifest["default"]:
            continue
        bundle = manifest.get("bundled")
        if not bundle:
            raise ValueError(f"Default dataset has no bundle: {manifest['id']}")
        path = (dictionaries / bundle["path"]).resolve()
        if not path.is_relative_to((dictionaries / "bundled").resolve()):
            raise ValueError("Bundled asset escapes the package.")
        if not path.is_file() or sha256(path.read_bytes()).hexdigest() != bundle["sha256"]:
            raise ValueError(f"Default dataset missing or changed: {manifest['id']}")
        for filename in bundle["license_files"]:
            path = (dictionaries / filename).resolve()
            if (
                not path.is_relative_to((dictionaries / "bundled").resolve())
                or not path.is_file()
                or not path.stat().st_size
            ):
                raise ValueError(f"Dataset notice missing or invalid: {filename}")
    bundled = dictionaries / "bundled"
    lock = json.loads((bundled / "SOURCES.json").read_text(encoding="utf-8"))
    notices = {
        name: data["sha256"] for name, data in lock["resources"].items() if data["kind"] == "notice"
    } | lock["derived_notices"]
    for name, expected in notices.items():
        if sha256((bundled / "licenses" / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Bundled license/documentation checksum mismatch: {name}")
    if (bundled / "NOTICE.txt").read_text(encoding="utf-8") != (
        ROOT / "THIRD_PARTY_NOTICES.md"
    ).read_text(encoding="utf-8"):
        raise ValueError("Dataset notice changed. Rebuild bundled assets before packaging.")


def build(output: Path, *, offline: bool = False) -> Path:
    source = ROOT / "src" / "katanki"
    try:
        verify_bundled_assets(source)
    except (OSError, ValueError):
        command = [sys.executable, str(ROOT / "scripts" / "bundle_datasets.py")]
        if offline:
            command.append("--offline")
        subprocess.run(command, check=True, cwd=ROOT)
        verify_bundled_assets(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.write(ROOT / "LICENSE", "LICENSE")
        archive.write(ROOT / "THIRD_PARTY_NOTICES.md", "THIRD_PARTY_NOTICES.md")
        for path in sorted(source.rglob("*")):
            if (
                path.is_file()
                and "__pycache__" not in path.parts
                and "user_files" not in path.relative_to(source).parts
                and "word_pack" not in path.relative_to(source).parts
                and path.suffix != ".pyc"
            ):
                archive.write(
                    path,
                    path.relative_to(source),
                    compress_type=ZIP_STORED if path.name == "jitendex.zip" else ZIP_DEFLATED,
                )
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--offline", action="store_true", help="Build from verified local cache only"
    )
    print(build(ROOT / "dist" / "kanji-katanki.ankiaddon", offline=parser.parse_args().offline))
