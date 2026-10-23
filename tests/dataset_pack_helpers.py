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
    date = version[:10].replace(".", "-") if "." in version else str(packs.revision(version))
    current = datetime.strptime(date, "%Y-%m-%d" if "." in version else "%Y%m%d").date()
    newer = current + timedelta(days=1)
    if "." in version:
        return f"{newer:%Y.%m.%d}.0"
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
    elif dataset_id == "jitendex":
        stream = io.BytesIO()
        with ZipFile(stream, "w") as archive:
            archive.writestr(
                "index.json",
                json.dumps(
                    {
                        "format": 3,
                        "revision": version,
                        "title": "Synthetic Jitendex",
                        "attribution": "Synthetic test dictionary",
                    }
                ),
            )
            archive.writestr(
                "term_bank_1.json",
                json.dumps(
                    [
                        ["景観", "けいかん", "★", "", 200, ["synthetic scenery"], 1, ""],
                    ]
                ),
            )
        payload, name, entries = stream.getvalue(), "jitendex.zip", 1
    else:
        stream = io.BytesIO()
        with ZipFile(stream, "w") as archive:
            archive.writestr("0666f.svg", (FIXTURES / "kanjivg/0666f.svg").read_bytes())
        payload, name, entries = stream.getvalue(), "kanjivg.zip", 1
    prefix = "bundled"
    files = {f"{prefix}/{name}": payload, f"{prefix}/NOTICE.txt": b"fixture attribution"}
    bundle = dict(
        path=f"{prefix}/{name}",
        version=version,
        entries=entries,
        sha256=sha256(payload).hexdigest(),
        license_files=[f"{prefix}/NOTICE.txt"],
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
