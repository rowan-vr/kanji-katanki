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
    manifest, release, payload = candidate()
    bundled = tmp_path / "dictionaries" / "bundled"
    bundled.mkdir(parents=True)
    (bundled / "old.txt").write_text("previous bundle")
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
