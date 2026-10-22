"""Prepare ignored build-time defaults from locked upstream sources."""

import argparse
import gzip
import json
import re
import shutil
import sys
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.request import HTTPRedirectHandler, Request, build_opener
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from katanki.dictionaries.adapters.kanjidic2_xml import KanjidicXml  # noqa: E402
from katanki.dictionaries.adapters.kanjivg_svg import KanjiVgSvg  # noqa: E402

DICTIONARIES = ROOT / "src" / "katanki" / "dictionaries"
BUNDLED = DICTIONARIES / "bundled"
CACHE = ROOT / "data" / "upstream"
MAX_SOURCE = 64 * 1024 * 1024


class _HttpsRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        if not newurl.startswith("https://"):
            raise ValueError("Dataset download redirected away from HTTPS.")
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def urlopen(request, *, timeout):
    return build_opener(_HttpsRedirect()).open(request, timeout=timeout)


def refresh_sources(lock: dict, cache: Path, *, update_lock: bool = True) -> None:
    """One generic bounded HTTPS fetcher, used only by maintainers on request."""
    cache.mkdir(parents=True, exist_ok=True)
    # Stage all inputs before replacing the cache, so failed fetches leave it intact.
    with TemporaryDirectory(dir=cache, prefix=".refresh-") as directory:
        stage = Path(directory)
        for name, source in lock["resources"].items():
            existing = cache / name
            if (
                not update_lock
                and existing.is_file()
                and sha256(existing.read_bytes()).hexdigest() == source["sha256"]
            ):
                continue
            url = source["url"]
            if not url.startswith("https://") or Path(name).name != name:
                raise ValueError("Expected HTTPS sources with simple cache filenames.")
            request = Request(
                url, headers={"User-Agent": "Mozilla/5.0 (Kanji Katanki data tooling)"}
            )
            with urlopen(request, timeout=30) as response:
                if not response.url.startswith("https://"):
                    raise ValueError("Upstream redirected away from HTTPS.")
                data = response.read(MAX_SOURCE + 1)
            if len(data) > MAX_SOURCE:
                raise ValueError(f"Upstream source is too large: {name}")
            digest = sha256(data).hexdigest()
            if not update_lock and digest != source["sha256"]:
                raise ValueError(
                    f"Upstream checksum changed: {name}. "
                    "Review an explicit --refresh; normal builds never update the lock."
                )
            (stage / name).write_bytes(data)
            if update_lock:
                source.update(sha256=digest, bytes=len(data))
        for path in stage.iterdir():
            path.replace(cache / path.name)


def verify_inputs(lock: dict, cache: Path) -> None:
    for name, source in lock["resources"].items():
        path = cache / name
        if not path.is_file() or sha256(path.read_bytes()).hexdigest() != source["sha256"]:
            raise ValueError(f"Missing or changed cached input: {name}. Use --refresh to update.")


def write_kanjidic(source: Path, target: Path):
    provider = KanjidicXml(source)
    root = ET.Element("kanjidic2")
    root.append(ET.Comment("KANJIDIC2 subset, CC BY-SA 4.0; see NOTICE.txt and licenses/."))
    header = ET.SubElement(root, "header")
    ET.SubElement(header, "date_of_creation").text = provider.version
    for character, entry in sorted(provider.entries.items()):
        node = ET.SubElement(root, "character")
        ET.SubElement(node, "literal").text = character
        misc = ET.SubElement(node, "misc")
        for key, value in (("grade", entry.grade), ("stroke_count", entry.stroke_count)):
            if value is not None:
                ET.SubElement(misc, key).text = str(value)
        group = ET.SubElement(ET.SubElement(node, "reading_meaning"), "rmgroup")
        for kind, readings in (("ja_on", entry.on_readings), ("ja_kun", entry.kun_readings)):
            for reading in readings:
                ET.SubElement(group, "reading", r_type=kind).text = reading
        for meaning in entry.meanings:
            ET.SubElement(group, "meaning").text = meaning
    xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    with (
        target.open("wb") as stream,
        gzip.GzipFile(
            fileobj=stream, filename="", mode="wb", mtime=0, compresslevel=9
        ) as compressed,
    ):
        compressed.write(xml)
    return provider.version, len(provider.entries)


def write_kanjivg(source: Path, target: Path, notices: Path):
    """Copy only canonical SVG members; never extract upstream archive paths."""
    count = 0
    with ZipFile(source) as upstream, ZipFile(target, "w", ZIP_DEFLATED) as output:
        if sum(info.file_size for info in upstream.infolist()) > 128 * 1024 * 1024:
            raise ValueError("Upstream KanjiVG ZIP exceeds expanded-size limit.")
        names = set()
        for info in sorted(upstream.infolist(), key=lambda info: info.filename):
            path = Path(info.filename)
            if (
                len(path.parts) != 3
                or path.parts[1] != "kanji"
                or not re.fullmatch(r"[0-9a-f]{5,6}\.svg", path.name)
            ):
                continue
            if path.name in names or info.file_size > 1024 * 1024:
                raise ValueError("Duplicate or oversized canonical SVG.")
            names.add(path.name)
            # Deterministic member timestamps and original, unmodified SVG bytes.
            member = ZipInfo(path.name, date_time=(1980, 1, 1, 0, 0, 0))
            # ZipInfo defaults to the host OS; pin Unix to keep locked hashes
            # identical on Windows and to match the Unix permissions below.
            member.create_system = 3
            member.compress_type = ZIP_DEFLATED
            member.external_attr = 0o644 << 16
            output.writestr(member, upstream.read(info))
            count += 1
        prefix = upstream.namelist()[0].split("/")[0]
        for filename in ("COPYING", "README.md"):
            (notices / f"KanjiVG-{filename}").write_bytes(upstream.read(f"{prefix}/{filename}"))
    if not count:
        raise ValueError("No canonical KanjiVG SVG files found.")
    return count


def bundle(*, refresh=False, offline=False):
    lock = json.loads((BUNDLED / "SOURCES.json").read_text(encoding="utf-8"))
    if not offline:
        refresh_sources(lock, CACHE, update_lock=refresh)
    verify_inputs(lock, CACHE)
    with TemporaryDirectory(dir=DICTIONARIES, prefix=".bundle-build-") as directory:
        stage = Path(directory) / "bundled"
        notices = stage / "licenses"
        notices.mkdir(parents=True)
        for name, source in lock["resources"].items():
            if source["kind"] == "notice":
                shutil.copyfile(CACHE / name, notices / name)
        version, kanji_count = write_kanjidic(
            CACHE / "kanjidic2.xml.gz", stage / "kanjidic2.xml.gz"
        )
        stroke_count = write_kanjivg(CACHE / "kanjivg-source.zip", stage / "kanjivg.zip", notices)
        lock["derived_notices"] = {
            path.name: sha256(path.read_bytes()).hexdigest()
            for path in notices.iterdir()
            if path.name.startswith("KanjiVG-")
        }
        shutil.copyfile(ROOT / "THIRD_PARTY_NOTICES.md", stage / "NOTICE.txt")
        (stage / "SOURCES.json").write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
        # Exercise the derived assets before publishing them into the source package.
        if len(KanjidicXml(stage / "kanjidic2.xml.gz").entries) != kanji_count:
            raise ValueError("Bundled KANJIDIC2 entry count changed during preparation.")
        with KanjiVgSvg(stage / "kanjivg.zip") as provider:
            if provider.lookup_strokes("景") is None:
                raise ValueError("Bundled KanjiVG is missing the smoke-test character.")
        metadata = {}
        for dataset_id, filename, dataset_version, count in (
            ("kanjidic2", "kanjidic2.xml.gz", version, kanji_count),
            ("kanjivg", "kanjivg.zip", lock["kanjivg_release"], stroke_count),
        ):
            license_files = ["bundled/NOTICE.txt", "bundled/SOURCES.json"] + [
                f"bundled/licenses/{path.name}" for path in sorted(notices.iterdir())
            ]
            metadata[dataset_id] = {
                "path": f"bundled/{filename}",
                "sha256": sha256((stage / filename).read_bytes()).hexdigest(),
                "version": dataset_version,
                "entries": count,
                "license_files": license_files,
            }
        if not refresh:
            for dataset_id, bundled in metadata.items():
                path = DICTIONARIES / "manifests" / f"{dataset_id}.json"
                expected = json.loads(path.read_text(encoding="utf-8"))["bundled"]
                if bundled != expected:
                    raise ValueError(
                        f"Generated {dataset_id} differs from locked metadata. "
                        "Review an explicit --refresh before building."
                    )
        previous = Path(directory) / "previous"
        BUNDLED.rename(previous)
        try:
            stage.rename(BUNDLED)
        except Exception:
            previous.rename(BUNDLED)
            raise
        for dataset_id, bundled in metadata.items() if refresh else ():
            path = DICTIONARIES / "manifests" / f"{dataset_id}.json"
            manifest = json.loads(path.read_text(encoding="utf-8"))
            manifest["bundled"] = bundled
            if dataset_id == "kanjivg":
                manifest["compression"] = ["none", "zip"]
            path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
    print(f"Bundled {kanji_count} kanji entries and {stroke_count} canonical stroke SVGs.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    options = parser.add_mutually_exclusive_group()
    options.add_argument(
        "--refresh", action="store_true", help="Fetch upstream sources and record new hashes"
    )
    options.add_argument("--offline", action="store_true", help="Require verified cached inputs")
    args = parser.parse_args()
    bundle(refresh=args.refresh, offline=args.offline)
