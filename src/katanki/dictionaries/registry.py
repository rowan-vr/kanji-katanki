"""Validate data-only manifests and map them to a fixed set of format adapters."""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

FORMATS = {"kanjidic2_xml", "kanjivg_svg", "jitendex_yomitan", "target_lists_json"}


@dataclass(frozen=True)
class DatasetManifest:
    id: str
    name: str
    format: str
    source: str
    capabilities: tuple[str, ...]
    compression: tuple[str, ...]
    version: str
    license_name: str
    license_url: str
    attribution: str
    default: bool
    bundled: dict | None = None


def _https(value):
    if not isinstance(value, str):
        raise ValueError("Manifest URLs must be HTTPS strings.")
    url = urlsplit(value)
    if url.scheme != "https" or not url.hostname or url.username or url.password:
        raise ValueError("Manifest URLs must use HTTPS without credentials.")
    return value


def read_manifest(path: Path) -> DatasetManifest:
    raw = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "id",
        "name",
        "format",
        "source",
        "capabilities",
        "compression",
        "version",
        "license",
        "default",
    }
    if not isinstance(raw, dict) or not required <= set(raw) or set(raw) - required - {"bundled"}:
        raise ValueError(f"Invalid manifest fields: {path.name}")
    for key in ("id", "name", "format", "version"):
        if not isinstance(raw[key], str) or not raw[key].strip():
            raise ValueError(f"Manifest {key} must be a nonempty string.")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", raw["id"]) or raw["format"] not in FORMATS:
        raise ValueError("Invalid dataset ID or unsupported format adapter.")
    expected = {
        "kanjidic2_xml": {"kanji"},
        "kanjivg_svg": {"strokes", "components"},
        "jitendex_yomitan": {"words"},
        "target_lists_json": {"target_lists"},
    }
    if (
        not isinstance(raw["capabilities"], list)
        or any(not isinstance(item, str) for item in raw["capabilities"])
        or len(set(raw["capabilities"])) != len(raw["capabilities"])
        or set(raw["capabilities"]) != expected[raw["format"]]
    ):
        raise ValueError("Capabilities do not match the format adapter.")
    if (
        not isinstance(raw["compression"], list)
        or not raw["compression"]
        or any(
            not isinstance(item, str) or item not in {"none", "gzip", "zip"}
            for item in raw["compression"]
        )
    ):
        raise ValueError("Invalid compression types.")
    if raw["format"] == "target_lists_json" and raw["compression"] != ["none"]:
        raise ValueError("Canonical target lists use uncompressed UTF-8 JSON.")
    license = raw["license"]
    if (
        not isinstance(license, dict)
        or set(license) != {"name", "url", "attribution"}
        or any(not isinstance(value, str) or not value.strip() for value in license.values())
        or type(raw["default"]) is not bool
    ):
        raise ValueError("Invalid license metadata or default flag.")
    bundled = raw.get("bundled")
    if bundled is not None:
        if (
            not isinstance(bundled, dict)
            or set(bundled) != {"path", "sha256", "version", "entries", "license_files"}
            or not isinstance(bundled["sha256"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", bundled["sha256"])
            or not isinstance(bundled["version"], str)
            or not bundled["version"].strip()
            or type(bundled["entries"]) is not int
            or bundled["entries"] <= 0
            or not isinstance(bundled["license_files"], list)
            or not bundled["license_files"]
        ):
            raise ValueError("Invalid bundled dataset metadata.")
        for filename in [bundled["path"], *bundled["license_files"]]:
            bundled_path(filename)
        if raw["format"] == "target_lists_json" and bundled["path"] != f"bundled/{raw['id']}.json":
            raise ValueError("Target dataset payload must use bundled/<dataset-id>.json.")
    return DatasetManifest(
        raw["id"],
        raw["name"],
        raw["format"],
        _https(raw["source"]),
        tuple(raw["capabilities"]),
        tuple(raw["compression"]),
        raw["version"],
        license["name"],
        _https(license["url"]),
        license["attribution"],
        raw["default"],
        bundled,
    )


def list_datasets(directory: Path | None = None) -> tuple[DatasetManifest, ...]:
    directory = directory or Path(__file__).with_name("manifests")
    manifests = tuple(read_manifest(path) for path in sorted(directory.glob("*.json")))
    if len({manifest.id for manifest in manifests}) != len(manifests):
        raise ValueError("Duplicate dataset IDs.")
    return manifests


def bundled_path(relative: str, root: Path | None = None) -> Path:
    """Resolve package-owned paths, never arbitrary manifest filesystem locations."""
    from pathlib import PurePosixPath

    root = root or Path(__file__).parent
    if (
        not isinstance(relative, str)
        or "\\" in relative
        or not relative.startswith("bundled/")
        or ".." in PurePosixPath(relative).parts
    ):
        raise ValueError("Bundled paths must stay inside dictionaries/bundled/.")
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Bundled path escapes the package.")
    return path


def bundled_sources() -> dict[str, Path]:
    return {
        manifest.id: bundled_path(manifest.bundled["path"])
        for manifest in list_datasets()
        if manifest.default and manifest.bundled
    }


def verify_bundle(manifest: DatasetManifest) -> None:
    from hashlib import sha256

    if manifest.bundled is None:
        raise ValueError(f"No bundled defaults configured for {manifest.name}.")
    path = bundled_path(manifest.bundled["path"])
    if not path.is_file() or sha256(path.read_bytes()).hexdigest() != manifest.bundled["sha256"]:
        raise ValueError(f"Bundled {manifest.name} is missing or corrupt. Reinstall the add-on.")
    for filename in manifest.bundled["license_files"]:
        if not bundled_path(filename).is_file():
            raise ValueError(f"Bundled {manifest.name} license/documentation file is missing.")
