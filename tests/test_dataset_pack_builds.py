"""Builds restore published, locked packs without touching live upstream URLs."""

import json
from dataclasses import replace
from io import BytesIO
from unittest.mock import Mock
from zipfile import ZipFile

import pytest
from dataset_pack_helpers import candidate

from scripts import dataset_packs


@pytest.fixture
def build_environment(tmp_path, monkeypatch):
    provenance = b'{"schema_version": 1, "resources": {}}\n'
    manifest, release, payload = candidate(extra={"bundled/SOURCES.json": provenance})
    bundled = tmp_path / "dictionaries" / "bundled"
    bundled.mkdir(parents=True)
    (bundled / "old.txt").write_text("previous bundle")
    (bundled / "SOURCES.json").write_bytes(provenance)
    lock = tmp_path / "lock.json"
    lock.write_text(json.dumps({"schema_version": 1, "datasets": {manifest.id: release}}))
    monkeypatch.setattr(dataset_packs, "BUNDLED", bundled)
    monkeypatch.setattr(dataset_packs, "LOCK", lock)
    monkeypatch.setattr(dataset_packs, "CACHE", tmp_path / "cache")
    # This lock intentionally describes a tiny, synthetic build default.
    with ZipFile(BytesIO(payload)) as archive:
        metadata = json.loads(archive.read("PACK.json"))
    monkeypatch.setattr(
        dataset_packs, "list_datasets", lambda: (replace(manifest, bundled=metadata["bundled"]),)
    )
    return manifest, release, payload, bundled


def test_cold_build_fetches_exact_pack_and_offline_rebuild_uses_cache(
    build_environment, monkeypatch
):
    _, release, payload, bundled = build_environment
    network = Mock(return_value=payload)
    monkeypatch.setattr(dataset_packs, "download", network)
    dataset_packs.restore()
    network.assert_called_once_with(release["url"], limit=release["bytes"])
    first = (bundled / "kanjidic2.xml").read_bytes()
    network.side_effect = AssertionError("Offline rebuild attempted a download")
    dataset_packs.restore(offline=True)
    assert (bundled / "kanjidic2.xml").read_bytes() == first
    assert not (bundled / "old.txt").exists()


@pytest.mark.parametrize("offline", [False, True])
def test_failed_build_preserves_prepared_defaults(build_environment, monkeypatch, offline):
    _, _, _, bundled = build_environment
    network = Mock(return_value=b"wrong checksum")
    monkeypatch.setattr(dataset_packs, "download", network)
    with pytest.raises(ValueError):
        dataset_packs.restore(offline=offline)
    assert (bundled / "old.txt").read_text() == "previous bundle"
    if offline:
        network.assert_not_called()


@pytest.mark.parametrize("changed", [False, True])
def test_provenance_accepts_crlf_but_rejects_changed_content(
    build_environment, monkeypatch, changed
):
    _, _, payload, bundled = build_environment
    source = bundled / "SOURCES.json"
    data = source.read_bytes().replace(b"\n", b"\r\n")
    if changed:
        data = data.replace(b'"schema_version": 1', b'"schema_version": 2')
    source.write_bytes(data)
    monkeypatch.setattr(dataset_packs, "download", Mock(return_value=payload))
    if changed:
        with pytest.raises(ValueError, match="tracked source provenance"):
            dataset_packs.restore()
        assert source.read_bytes() == data
        assert (bundled / "old.txt").exists()
    else:
        dataset_packs.restore()
        assert source.read_bytes().endswith(b"\n")
        assert b"\r" not in source.read_bytes()


def test_jitendex_uses_the_same_bundled_release_pack_restore(tmp_path, monkeypatch):
    manifest, release, payload = candidate(dataset_id="jitendex")
    bundled = tmp_path / "dictionaries/bundled"
    bundled.mkdir(parents=True)
    (bundled / "old.txt").write_text("Keep unrelated dictionary")
    lock = tmp_path / "lock.json"
    lock.write_text(json.dumps({"schema_version": 1, "datasets": {manifest.id: release}}))
    with ZipFile(BytesIO(payload)) as archive:
        metadata = json.loads(archive.read("PACK.json"))
    monkeypatch.setattr(dataset_packs, "BUNDLED", bundled)
    monkeypatch.setattr(dataset_packs, "LOCK", lock)
    monkeypatch.setattr(dataset_packs, "CACHE", tmp_path / "cache")
    monkeypatch.setattr(
        dataset_packs, "list_datasets", lambda: (replace(manifest, bundled=metadata["bundled"]),)
    )
    monkeypatch.setattr(dataset_packs, "download", Mock(return_value=payload))
    dataset_packs.restore()
    assert (bundled / "jitendex.zip").is_file()
    assert not (bundled / "old.txt").exists()
    dataset_packs.restore(offline=True)


def test_all_defaults_restore_from_one_release_lock_without_upstream_fallback(
    tmp_path, monkeypatch
):
    provenance = b'{"schema_version": 1, "resources": {}}\n'
    candidates = [
        candidate(dataset_id=key, extra={"bundled/SOURCES.json": provenance})
        for key in ("kanjidic2", "kanjivg", "jitendex")
    ]
    manifests, releases, responses = [], {}, {}
    for manifest, release, payload in candidates:
        with ZipFile(BytesIO(payload)) as archive:
            metadata = json.loads(archive.read("PACK.json"))
        manifests.append(replace(manifest, bundled=metadata["bundled"]))
        releases[manifest.id] = release
        responses[release["url"]] = payload
    bundled = tmp_path / "dictionaries/bundled"
    bundled.mkdir(parents=True)
    (bundled / "SOURCES.json").write_bytes(provenance)
    lock = tmp_path / "lock.json"
    lock.write_text(json.dumps({"schema_version": 1, "datasets": releases}))
    monkeypatch.setattr(dataset_packs, "BUNDLED", bundled)
    monkeypatch.setattr(dataset_packs, "LOCK", lock)
    monkeypatch.setattr(dataset_packs, "CACHE", tmp_path / "cache")
    monkeypatch.setattr(dataset_packs, "list_datasets", lambda: tuple(manifests))
    network = Mock(side_effect=lambda url, **kwargs: responses[url])
    monkeypatch.setattr(dataset_packs, "download", network)
    dataset_packs.restore()
    assert {call.args[0] for call in network.call_args_list} == set(responses)
    assert all(
        (bundled / name).is_file() for name in ("kanjidic2.xml", "kanjivg.zip", "jitendex.zip")
    )
    network.reset_mock()
    network.side_effect = AssertionError("Offline build attempted a download")
    dataset_packs.restore(offline=True)
    network.assert_not_called()
    # Missing entries fail closed; a build must not switch to a special raw-source fetch.
    del releases["jitendex"]
    lock.write_text(json.dumps({"schema_version": 1, "datasets": releases}))
    with pytest.raises(ValueError, match="every default"):
        dataset_packs.restore()
    network.assert_not_called()
    assert (bundled / "jitendex.zip").is_file()
