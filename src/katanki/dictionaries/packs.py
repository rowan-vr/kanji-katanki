"""Validate versioned data-only packs without extracting untrusted archive paths."""

import io
import json
import re
from hashlib import sha256
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile

from .downloads import https_url
from .registry import bundled_path, list_datasets

FORMAT_VERSION = 1
MAX_PACK = 64 * 1024 * 1024
MAX_EXPANDED = 160 * 1024 * 1024
RELEASE_PREFIX = "https://github.com/rowan-vr/kanji-katanki/releases/download/datasets-"


def revision(version: str) -> int:
    """Current datasets use dated versions: YYYY-MM-DD or rYYYYMMDD."""
    digits = "".join(re.findall(r"\d", version))
    if len(digits) != 8:
        raise ValueError("Dictionary versions must contain an eight-digit date.")
    return int(digits)


def read_catalog(raw: dict) -> dict[str, dict]:
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise ValueError("Unsupported dictionary catalog.")
    entries = raw.get("datasets")
    if not isinstance(entries, dict):
        raise ValueError("Invalid dictionary catalog entries.")
    known = {item.id for item in list_datasets()}
    result = {}
    for dataset_id, entry in entries.items():
        if dataset_id not in known:
            continue  # Future datasets are irrelevant to older add-ons.
        if not isinstance(entry, dict) or type(entry.get("format_version")) is not int:
            raise ValueError("Invalid dictionary format version.")
        if entry["format_version"] != FORMAT_VERSION:
            continue
        if (
            not isinstance(entry.get("version"), str)
            or type(entry.get("revision")) is not int
            or entry["revision"] != revision(entry["version"])
            or not isinstance(entry.get("sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])
            or type(entry.get("bytes")) is not int
            or not 0 < entry["bytes"] <= MAX_PACK
            or not isinstance(entry.get("url"), str)
            or not entry["url"].startswith(RELEASE_PREFIX)
        ):
            raise ValueError(f"Invalid dictionary release: {dataset_id}")
        url = https_url(entry["url"])
        # Require a dataset tag and a single asset filename, with no query/fragment.
        suffix = url.removeprefix(RELEASE_PREFIX)
        if not re.fullmatch(r"[A-Za-z0-9._-]+/[A-Za-z0-9._-]+\.zip", suffix):
            raise ValueError("Invalid dictionary release asset URL.")
        result[dataset_id] = dict(entry)
    return result


def verify_download(data: bytes, release: dict) -> None:
    if len(data) != release["bytes"] or sha256(data).hexdigest() != release["sha256"]:
        raise ValueError("Dictionary pack size or SHA-256 mismatch. Existing data was preserved.")


def unpack(data: bytes, dataset_id: str, release: dict, destination: Path) -> dict:
    """Write only explicitly listed, canonical data paths to a private staging directory."""
    verify_download(data, release)
    try:
        return _unpack(data, dataset_id, release, destination)
    except (BadZipFile, KeyError, TypeError, AttributeError, RuntimeError) as error:
        raise ValueError("Invalid dictionary pack contents or metadata.") from error


def _unpack(data: bytes, dataset_id: str, release: dict, destination: Path) -> dict:
    with ZipFile(io.BytesIO(data)) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if (
            len(names) != len(set(names))
            or len(names) > 32
            or sum(info.file_size for info in infos) > MAX_EXPANDED
        ):
            raise ValueError("Duplicate files or excessive expanded dictionary pack size.")
        info = archive.getinfo("PACK.json")
        if info.file_size > 64 * 1024:
            raise ValueError("Dictionary pack metadata is too large.")
        metadata = json.loads(archive.read(info))
        bundle = metadata.get("bundled", {})
        if (
            metadata.get("id") != dataset_id
            or metadata.get("format_version") != FORMAT_VERSION
            or metadata.get("revision") != release["revision"]
            or bundle.get("version") != release["version"]
        ):
            raise ValueError("Dictionary pack does not match the requested release.")
        files = metadata.get("files")
        if not isinstance(files, dict) or set(names) != {"PACK.json", *files}:
            raise ValueError("Dictionary pack file list does not match its metadata.")
        if (
            not isinstance(bundle.get("license_files"), list)
            or not bundle["license_files"]
            or type(bundle.get("entries")) is not int
            or bundle["entries"] <= 0
            or not isinstance(bundle.get("path"), str)
            or set(files) != {bundle["path"], *bundle["license_files"]}
            or files.get(bundle["path"]) != bundle.get("sha256")
        ):
            raise ValueError("Incomplete dictionary payload or license metadata.")
        filename = {"kanjidic2": "kanjidic2.xml", "kanjivg": "kanjivg.zip"}[dataset_id]
        if bundle["path"] != f"bundled/{filename}":
            raise ValueError("Unexpected dictionary payload filename.")
        for name, expected in files.items():
            path = PurePosixPath(name)
            if (
                "\\" in name
                or ".." in path.parts
                or str(path) != name
                or not name.startswith("bundled/")
                or path.suffix not in {".xml", ".zip", ".txt", ".json", ".html", ".md", ""}
            ):
                raise ValueError("Unexpected file path in dictionary pack.")
            target = bundled_path(name, destination)
            payload = archive.read(name)
            if not payload or sha256(payload).hexdigest() != expected:
                raise ValueError(f"Dictionary pack file checksum mismatch: {name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
    validate_contents(dataset_id, destination, bundle)
    (destination / "PACK.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata


def validate_contents(dataset_id: str, root: Path, bundle: dict) -> None:
    from .adapters.kanjidic2_xml import KanjidicXml
    from .adapters.kanjivg_svg import KanjiVgSvg

    path = bundled_path(bundle["path"], root)
    if dataset_id == "kanjidic2":
        provider = KanjidicXml(path)
        if (
            len(provider.entries) != bundle["entries"]
            or provider.version != bundle["version"]
            or provider.lookup_kanji("景") is None
        ):
            raise ValueError("Dictionary pack has invalid KANJIDIC2 contents.")
    else:
        with KanjiVgSvg(path) as provider:
            names = provider.archive.namelist()
            if (
                len(names) != bundle["entries"]
                or len(names) != len(set(names))
                or any(not re.fullmatch(r"[0-9a-f]{5,6}\.svg", name) for name in names)
                or provider.lookup_strokes("景") is None
            ):
                raise ValueError("Dictionary pack has invalid KanjiVG contents.")
