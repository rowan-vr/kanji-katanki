"""Data updates use trusted metadata and preserve offline defaults on every failure."""

import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from unittest.mock import Mock

import pytest
from dataset_pack_helpers import candidate, next_version

from katanki.config import DictionaryChoice
from katanki.dictionaries import packs, updates
from katanki.dictionaries.manager import DictionaryManager
from katanki.dictionaries.preferences import dictionary_sources
from katanki.dictionaries.registry import bundled_path, list_datasets

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def storage(tmp_path, monkeypatch):
    monkeypatch.setattr(updates, "USER_DATA", tmp_path / "user_files" / "dictionaries")
    return updates.USER_DATA


def test_install_update_is_used_offline_with_provenance_and_revert(storage, monkeypatch):
    manifest, release, payload = candidate()
    network = Mock(return_value=payload)
    monkeypatch.setattr(updates, "download", network)
    assert updates.default_source(manifest) == bundled_path(manifest.bundled["path"])
    assert updates.install(manifest, release) == release["version"]
    network.side_effect = AssertionError("Offline use attempted a download")
    selected = dictionary_sources((DictionaryChoice("kanjivg", "disabled"),))
    assert selected[manifest.id].is_relative_to(storage)
    with DictionaryManager(selected) as manager:
        assert manager.lookup_kanji("景").meanings == ("fixture scenery",)
        details = "\n".join(manager.source_details())
        assert release["version"] in details and "downloaded SHA-256" in details
    assert updates.available(manifest, {manifest.id: release}) is None
    updates.use_bundled(manifest.id)
    assert updates.default_source(manifest) == bundled_path(manifest.bundled["path"])
    assert network.call_count == 1


def test_local_and_disabled_choices_remain_independent_of_installed_updates(storage, monkeypatch):
    manifest, release, payload = candidate()
    monkeypatch.setattr(updates, "download", Mock(return_value=payload))
    updates.install(manifest, release)
    choices = (
        DictionaryChoice("kanjidic2", "local", str(FIXTURES / "kanjidic2.xml")),
        DictionaryChoice("kanjivg", "disabled"),
    )
    assert dictionary_sources(choices) == {"kanjidic2": FIXTURES / "kanjidic2.xml"}


@pytest.mark.parametrize("failure", ["network", "hash", "archive", "contents", "activation"])
def test_failed_update_preserves_active_pack(storage, monkeypatch, failure):
    manifest, release, payload = candidate()
    network = Mock(return_value=payload)
    monkeypatch.setattr(updates, "download", network)
    updates.install(manifest, release)
    original = (storage / "active.json").read_bytes()
    before = updates.default_source(manifest)
    _, newer, data = candidate(version=next_version(release["version"]))
    if failure == "network":
        network.side_effect = OSError("offline")
    elif failure == "hash":
        network.return_value = b"wrong bytes"
    elif failure == "archive":
        network.return_value = b"not a ZIP"
        newer.update(
            bytes=len(network.return_value), sha256=sha256(network.return_value).hexdigest()
        )
    elif failure == "contents":
        network.return_value = data
        monkeypatch.setattr(
            packs, "validate_contents", Mock(side_effect=ValueError("invalid data"))
        )
    else:
        network.return_value = data
        original_write = updates._write

        def fail_activation(name, value):
            if name == "active.json":
                raise OSError("disk full")
            original_write(name, value)

        monkeypatch.setattr(updates, "_write", fail_activation)
    with pytest.raises((OSError, ValueError)):
        updates.install(manifest, newer)
    assert (storage / "active.json").read_bytes() == original
    assert updates.default_source(manifest) == before


def test_corrupt_downloaded_data_falls_back_and_newer_bundles_win(storage, monkeypatch):
    manifest, release, data = candidate()
    monkeypatch.setattr(updates, "download", Mock(return_value=data))
    updates.install(manifest, release)
    newer_bundle = replace(
        manifest, bundled=manifest.bundled | {"version": next_version(release["version"])}
    )
    assert updates.installed(newer_bundle) is None
    assert updates.default_source(newer_bundle) == bundled_path(manifest.bundled["path"])
    updates.default_source(manifest).write_bytes(b"damaged")
    assert updates.default_source(manifest) == bundled_path(manifest.bundled["path"])


@pytest.mark.parametrize(
    "path", ["bundled/../../outside.txt", "bundled/code.py", "bundled//bad.txt"]
)
def test_pack_rejects_unexpected_paths(storage, monkeypatch, path):
    manifest, release, data = candidate(extra={path: b"unexpected"})
    monkeypatch.setattr(updates, "download", Mock(return_value=data))
    with pytest.raises(ValueError):
        updates.install(manifest, release)
    assert not (storage / "active.json").exists()
    assert updates.installed(manifest) is None


def test_stroke_pack_validates_and_preserves_licenses(storage, monkeypatch):
    manifest, release, data = candidate(dataset_id="kanjivg")
    monkeypatch.setattr(updates, "download", Mock(return_value=data))
    updates.install(manifest, release)
    current = updates.installed(manifest)
    assert current is not None
    assert bundled_path("bundled/NOTICE.txt", current[0]).read_text() == "fixture attribution"
    with DictionaryManager({manifest.id: updates.default_source(manifest)}) as manager:
        assert manager.lookup_strokes("景") is not None
        assert release["version"] in manager.source_details()[0]


def test_catalog_check_caches_results_throttles_and_survives_outages(storage, monkeypatch):
    manifest, release, _ = candidate()
    raw = {"schema_version": 1, "datasets": {manifest.id: release}}
    network = Mock(return_value=json.dumps(raw).encode())
    monkeypatch.setattr(updates, "download", network)
    monkeypatch.setattr(updates.time, "time", lambda: 200000)
    assert updates.check_updates(automatic=True) == {}
    network.assert_not_called()
    updates.set_automatic(True)
    assert updates.check_updates(automatic=True) == raw["datasets"]
    assert updates.check_updates(automatic=True) == raw["datasets"]
    assert network.call_count == 1
    network.side_effect = OSError("offline")
    with pytest.raises(OSError):
        updates.check_updates()
    assert updates.cached_catalog() == raw["datasets"]
    assert updates.preferences()["last_success"] == 200000
    assert updates.preferences()["error"] == "offline"
    assert updates.default_source(manifest) == bundled_path(manifest.bundled["path"])


def test_catalog_ignores_future_formats_and_rejects_untrusted_downloads():
    manifest, release, _ = candidate()
    raw = {"schema_version": 1, "datasets": {manifest.id: release | {"format_version": 2}}}
    assert packs.read_catalog(raw) == {}
    raw["datasets"][manifest.id] = release | {"url": "https://example.org/dictionary.zip"}
    with pytest.raises(ValueError, match="Invalid dictionary release"):
        packs.read_catalog(raw)


def test_malformed_local_state_does_not_break_offline_defaults(storage):
    storage.mkdir(parents=True)
    (storage / "active.json").write_text("not JSON")
    manifest = list_datasets()[0]
    assert updates.installed(manifest) is None
    assert updates.default_source(manifest) == bundled_path(manifest.bundled["path"])
