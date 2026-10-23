"""Synthetic, redistributable packs for unit tests and real-host UI checks."""

import io
import json
from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from katanki.dictionaries import packs
from katanki.dictionaries.registry import list_datasets

FIXTURES = Path(__file__).parent / "fixtures"


def next_version(version):
    current = datetime.strptime(str(packs.revision(version)), "%Y%m%d").date()
    newer = current + timedelta(days=1)
    return f"r{newer:%Y%m%d}" if version.startswith("r") else newer.isoformat()


def candidate(*, version=None, dataset_id="kanjidic2", extra=None):
    manifest = next(item for item in list_datasets() if item.id == dataset_id)
    version = version or next_version(manifest.bundled["version"])
    if dataset_id == "kanjidic2":
        payload = (
            (FIXTURES / "kanjidic2.xml")
            .read_bytes()
            .replace(b"2026-10-22 (synthetic fixture)", version.encode())
        )
        name, entries = "kanjidic2.xml", 2
    else:
        stream = io.BytesIO()
        with ZipFile(stream, "w") as archive:
            archive.writestr("0666f.svg", (FIXTURES / "kanjivg/0666f.svg").read_bytes())
        payload, name, entries = stream.getvalue(), "kanjivg.zip", 1
    files = {f"bundled/{name}": payload, "bundled/NOTICE.txt": b"fixture attribution"}
    bundle = dict(
        path=f"bundled/{name}",
        version=version,
        entries=entries,
        sha256=sha256(payload).hexdigest(),
        license_files=["bundled/NOTICE.txt"],
    )
    if extra:
        files.update(extra)
        bundle["license_files"].extend(extra)
    metadata = dict(
        id=dataset_id,
        format_version=1,
        revision=packs.revision(version),
        bundled=bundle,
        files={name: sha256(value).hexdigest() for name, value in files.items()},
    )
    stream = io.BytesIO()
    with ZipFile(stream, "w", ZIP_DEFLATED) as archive:
        archive.writestr("PACK.json", json.dumps(metadata))
        for name, value in files.items():
            archive.writestr(name, value)
    data = stream.getvalue()
    release = dict(
        version=version,
        revision=packs.revision(version),
        format_version=1,
        url=packs.RELEASE_PREFIX + "fixture/" + dataset_id + ".zip",
        sha256=sha256(data).hexdigest(),
        bytes=len(data),
    )
    return manifest, release, data
