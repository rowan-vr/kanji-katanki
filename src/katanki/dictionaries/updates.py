"""Persistent, optional dictionary updates with an offline bundled fallback."""

import json
import logging
import re
import threading
import time
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from uuid import uuid4

from .downloads import download
from .packs import read_catalog, revision, unpack
from .registry import bundled_path

CATALOG_URL = "https://raw.githubusercontent.com/rowan-vr/kanji-katanki/main/datasets/catalog.json"
USER_DATA: Path | None = None
_LOCK = threading.RLock()
logger = logging.getLogger(__name__)


def configure_storage(directory: Path | None) -> None:
    global USER_DATA
    USER_DATA = directory


def _storage() -> Path:
    if USER_DATA is None:
        raise ValueError("Dictionary update storage is not configured. Open Settings in Anki.")
    USER_DATA.mkdir(parents=True, exist_ok=True)
    return USER_DATA


def _read(name: str) -> dict:
    if USER_DATA is None:
        return {}
    try:
        value = json.loads((USER_DATA / name).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(name: str, value: dict) -> None:
    root = _storage()
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=root, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(value, stream, indent=2)
            stream.write("\n")
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.replace(root / name)
    finally:
        temporary.unlink(missing_ok=True)


def preferences() -> dict:
    return _read("checks.json")


def set_automatic(enabled: bool) -> None:
    with _LOCK:
        state = preferences()
        state["automatic"] = bool(enabled)
        _write("checks.json", state)


def check_updates(*, automatic: bool = False) -> dict[str, dict]:
    with _LOCK:
        state = preferences()
        now = time.time()
        if automatic and (
            not state.get("automatic", False) or now - state.get("last_attempt", 0) < 86400
        ):
            return cached_catalog()
        state["last_attempt"] = now
        _write("checks.json", state)
        try:
            raw = json.loads(download(CATALOG_URL, limit=256 * 1024))
            releases = read_catalog(raw)
            _write("catalog.json", raw)
        except Exception as error:
            state["error"] = str(error)
            _write("checks.json", state)
            raise
        state.update(last_success=now, error="")
        _write("checks.json", state)
        return releases


def cached_catalog() -> dict[str, dict]:
    try:
        return read_catalog(_read("catalog.json"))
    except ValueError:
        return {}


def installed(manifest) -> tuple[Path, dict] | None:
    """Verify installed files before use; any damage falls back to packaged defaults."""
    if USER_DATA is None:
        return None
    try:
        active = _read("active.json").get(manifest.id)
        if not isinstance(active, dict) or not re.fullmatch(r"[0-9a-f]{32}", active["directory"]):
            return None
        release = read_catalog({"schema_version": 1, "datasets": {manifest.id: active["release"]}})[
            manifest.id
        ]
        if manifest.bundled and release["revision"] <= revision(manifest.bundled["version"]):
            return None
        root = USER_DATA / "packs" / manifest.id / active["directory"]
        metadata = json.loads((root / "PACK.json").read_text(encoding="utf-8"))
        bundle = metadata["bundled"]
        if (
            metadata["id"] != manifest.id
            or metadata["format_version"] != release["format_version"]
            or metadata["revision"] != release["revision"]
            or bundle["version"] != release["version"]
            or metadata["files"][bundle["path"]] != bundle["sha256"]
        ):
            raise ValueError("Installed dictionary metadata changed.")
        for name, digest in metadata["files"].items():
            if sha256(bundled_path(name, root).read_bytes()).hexdigest() != digest:
                raise ValueError(f"Installed dictionary file changed: {name}")
        return root, metadata
    except (OSError, ValueError, KeyError, TypeError):
        logger.warning("Downloaded %s unavailable; using bundled defaults", manifest.id)
        return None


def default_source(manifest) -> Path:
    current = installed(manifest)
    if current:
        root, metadata = current
        return bundled_path(metadata["bundled"]["path"], root)
    if manifest.bundled is None:
        raise ValueError(f"No default dictionary available for {manifest.name}.")
    return bundled_path(manifest.bundled["path"])


def available(manifest, catalog: dict | None = None) -> dict | None:
    release = (cached_catalog() if catalog is None else catalog).get(manifest.id)
    current = installed(manifest)
    current_revision = current[1]["revision"] if current else revision(manifest.bundled["version"])
    return release if release and release["revision"] > current_revision else None


def install(manifest, release: dict) -> str:
    with _LOCK:
        release = read_catalog({"schema_version": 1, "datasets": {manifest.id: release}}).get(
            manifest.id
        )
        if release is None or available(manifest, {manifest.id: release}) is None:
            raise ValueError("No newer compatible dictionary update is available.")
        data = download(release["url"], limit=release["bytes"])
        root = _storage()
        with TemporaryDirectory(dir=root, prefix=".install-") as directory:
            stage = Path(directory) / "pack"
            stage.mkdir()
            unpack(data, manifest.id, release, stage)
            identifier = uuid4().hex
            destination = root / "packs" / manifest.id / identifier
            destination.parent.mkdir(parents=True, exist_ok=True)
            stage.rename(destination)
            active = _read("active.json")
            active[manifest.id] = {"directory": identifier, "release": release}
            _write("active.json", active)
        return release["version"]


def use_bundled(dataset_id: str) -> None:
    with _LOCK:
        active = _read("active.json")
        active.pop(dataset_id, None)
        _write("active.json", active)
