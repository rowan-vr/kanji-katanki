import io
import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from unittest.mock import Mock
from zipfile import ZipFile, ZipInfo

import pytest

from katanki.common.models import ScanResult
from katanki.dictionaries.adapters.kanjivg_svg import KanjiVgSvg
from katanki.dictionaries.manager import DictionaryManager
from katanki.dictionaries.registry import (
    bundled_path,
    bundled_sources,
    list_datasets,
    verify_bundle,
)
from katanki.generation.discovery.report import classify_scan
from scripts.bundle_datasets import refresh_sources

requires_datasets = pytest.mark.skipif(
    not all(path.is_file() for path in bundled_sources().values()),
    reason="Build the add-on first to run bundled-data verification (no unit-test downloads).",
)


@requires_datasets
def test_defaults_load_offline_with_licenses_and_versioned_fingerprints(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", Mock(side_effect=AssertionError("Network used")))
    with DictionaryManager() as manager:
        assert manager.status() == ("components", "kanji", "strokes")
        assert manager.lookup_kanji("景").meanings != ("fixture scenery",)
        assert manager.lookup_strokes("景") is not None
        for manifest in list_datasets():
            assert manifest.bundled["version"] in " ".join(manager.source_details())
    for manifest in list_datasets():
        verify_bundle(manifest)
        assert manifest.bundled["entries"] > 6000
    assert "CC BY-SA 4.0" in bundled_path("bundled/NOTICE.txt").read_text()
    assert "CC BY-SA 3.0" in bundled_path("bundled/NOTICE.txt").read_text()


@requires_datasets
def test_corrupt_bundle_is_rejected():
    manifest = list_datasets()[0]
    broken = replace(manifest, bundled=manifest.bundled | {"sha256": "0" * 64})
    with pytest.raises(ValueError, match="missing or corrupt"):
        verify_bundle(broken)


@pytest.mark.parametrize(
    "path", ["../secret", "/tmp/secret", "bundled/../../secret", r"bundled\secret"]
)
def test_bundle_paths_cannot_escape_package(path):
    with pytest.raises(ValueError):
        bundled_path(path)


@requires_datasets
def test_shipped_stroke_coverage_and_known_upstream_metadata_issue():
    with DictionaryManager() as manager:
        with ZipFile(bundled_sources()["kanjivg"]) as archive:
            characters = tuple(
                sorted(
                    character
                    for filename in archive.namelist()
                    if manager.lookup_kanji(character := chr(int(Path(filename).stem, 16)))
                    is not None
                )
            )
        report = classify_scan(ScanResult(0, characters), manager, manager)
    # Pinned r20260714 labels 06a45.svg's root as 機, not 橅. Do not silently
    # show a potentially mislabelled diagram. Revisit this expectation on refresh.
    assert len(report.entries) == 6417
    assert len(report.strokes) == 6416
    assert len(report.warnings) == 1 and report.warnings[0].startswith("橅:")


def test_zip_lookup_never_extracts_traversal_members(tmp_path):
    fixture = Path(__file__).parent / "fixtures/kanjivg/0666f.svg"
    path = tmp_path / "strokes.zip"
    with ZipFile(path, "w") as archive:
        archive.writestr("../../outside.svg", fixture.read_bytes())
        archive.writestr("0666f.svg", fixture.read_bytes())
    with KanjiVgSvg(path) as provider:
        assert provider.lookup_strokes("景") is not None
    assert not (tmp_path.parent / "outside.svg").exists()


def test_kanjivg_bundle_is_identical_across_creator_platforms(tmp_path, monkeypatch):
    from scripts import bundle_datasets

    svg = (Path(__file__).parent / "fixtures/kanjivg/0666f.svg").read_bytes()
    source = tmp_path / "upstream.zip"
    with ZipFile(source, "w") as archive:
        archive.writestr("release/kanji/0666f.svg", svg)
        archive.writestr("release/COPYING", b"license")
        archive.writestr("release/README.md", b"documentation")
    notices = tmp_path / "licenses"
    notices.mkdir()
    outputs = []
    for platform in (0, 3):  # Windows and Unix ZipInfo defaults.
        def host_zip_info(*args, platform=platform, **kwargs):
            member = ZipInfo(*args, **kwargs)
            member.create_system = platform
            return member

        monkeypatch.setattr(bundle_datasets, "ZipInfo", host_zip_info)
        target = tmp_path / f"kanjivg-{platform}.zip"
        assert bundle_datasets.write_kanjivg(source, target, notices) == 1
        with ZipFile(target) as archive:
            assert archive.read("0666f.svg") == svg
            assert archive.getinfo("0666f.svg").create_system == 3
        outputs.append(target.read_bytes())
    assert outputs[0] == outputs[1]


def test_failed_refresh_preserves_cached_inputs(tmp_path, monkeypatch):
    from scripts import bundle_datasets

    cache = tmp_path / "upstream"
    cache.mkdir()
    (cache / "one").write_bytes(b"old")
    lock = {
        "resources": {
            "one": {"url": "https://example.org/one"},
            "two": {"url": "https://example.org/two"},
        }
    }
    first = io.BytesIO(b"new")
    first.url = "https://example.org/one"
    monkeypatch.setattr(bundle_datasets, "urlopen", Mock(side_effect=[first, OSError("offline")]))
    with pytest.raises(OSError, match="offline"):
        refresh_sources(lock, cache)
    assert (cache / "one").read_bytes() == b"old"
    assert not (cache / "two").exists()


@requires_datasets
def test_bundled_notice_copies_match_locked_upstream_sources():
    lock = json.loads(bundled_path("bundled/SOURCES.json").read_text())
    for filename, resource in lock["resources"].items():
        if resource["kind"] == "notice":
            path = bundled_path(f"bundled/licenses/{filename}")
            assert sha256(path.read_bytes()).hexdigest() == resource["sha256"]


def test_locked_download_rejects_changed_upstream_without_replacing_cache(tmp_path, monkeypatch):
    from scripts import bundle_datasets

    lock = {"resources": {"data": {"url": "https://example.org/data", "sha256": "0" * 64}}}
    response = io.BytesIO(b"unexpected")
    response.url = "https://example.org/data"
    monkeypatch.setattr(bundle_datasets, "urlopen", Mock(return_value=response))
    with pytest.raises(ValueError, match="Upstream checksum changed"):
        refresh_sources(lock, tmp_path, update_lock=False)
    assert not (tmp_path / "data").exists()
    assert lock["resources"]["data"]["sha256"] == "0" * 64


def test_locked_download_reuses_verified_cache_without_network(tmp_path, monkeypatch):
    from scripts import bundle_datasets

    payload = b"verified cached source"
    (tmp_path / "data").write_bytes(payload)
    lock = {
        "resources": {
            "data": {
                "url": "https://example.org/data",
                "sha256": sha256(payload).hexdigest(),
            }
        }
    }
    network = Mock(side_effect=AssertionError("Unexpected download"))
    monkeypatch.setattr(bundle_datasets, "urlopen", network)
    refresh_sources(lock, tmp_path, update_lock=False)
    network.assert_not_called()


def test_locked_download_accepts_expected_bytes_without_changing_lock(tmp_path, monkeypatch):
    from scripts import bundle_datasets

    payload = b"pinned upstream content"
    expected = sha256(payload).hexdigest()
    lock = {"resources": {"data": {"url": "https://example.org/data", "sha256": expected}}}
    response = io.BytesIO(payload)
    response.url = "https://example.org/data"
    monkeypatch.setattr(bundle_datasets, "urlopen", Mock(return_value=response))
    refresh_sources(lock, tmp_path, update_lock=False)
    assert (tmp_path / "data").read_bytes() == payload
    assert lock["resources"]["data"]["sha256"] == expected
