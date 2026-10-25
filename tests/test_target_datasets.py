"""Target classifications share the dictionary release/install/build lifecycle."""

import io
import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from unittest.mock import Mock
from zipfile import ZipFile

import pytest
from dataset_pack_helpers import candidate
from test_target_lists import example_list

from katanki.config import DictionaryChoice
from katanki.dictionaries import packs, preferences, registry, updates
from katanki.dictionaries.manager import DictionaryManager
from katanki.stats.sources import load_target_registry
from katanki.stats.targets import parse_target_list
from scripts import bundle_datasets, dataset_packs


def target_pack(manifest, *, version="2026-10-25", change=None):
    raw = example_list(manifest.id + ":levels")
    raw["version"] = version
    raw["source"].update(
        url="https://example.org/synthetic-source.json",
        revision=version,
        authority="unofficial",
        sha256="1" * 64,
    )
    if change:
        change(raw)
    payload = json.dumps(raw, ensure_ascii=False).encode()
    files = {
        manifest.bundled["path"]: payload,
        "bundled/NOTICE.txt": b"Synthetic redistribution notice",
    }
    bundle = dict(
        manifest.bundled,
        version=version,
        entries=3,
        sha256=sha256(payload).hexdigest(),
        license_files=["bundled/NOTICE.txt"],
    )
    metadata = {
        "id": manifest.id,
        "format_version": 1,
        "revision": packs.revision(version),
        "bundled": bundle,
        "files": {name: sha256(data).hexdigest() for name, data in files.items()},
    }
    stream = io.BytesIO()
    with ZipFile(stream, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
        archive.writestr("PACK.json", json.dumps(metadata))
    data = stream.getvalue()
    release = dict(
        version=version,
        revision=metadata["revision"],
        format_version=1,
        bytes=len(data),
        sha256=sha256(data).hexdigest(),
        url=packs.RELEASE_PREFIX + "synthetic-targets/" + manifest.id + ".zip",
    )
    return release, data, metadata


@pytest.fixture
def target_manifests(tmp_path, monkeypatch):
    existing = tuple(m for m in registry.list_datasets() if m.format != "target_lists_json")
    original = next(item for item in existing if item.id == "kanjidic2")
    manifests = tuple(
        replace(
            original,
            id=dataset_id,
            name="Synthetic " + dataset_id,
            format="target_lists_json",
            capabilities=("target_lists",),
            compression=("none",),
            bundled=original.bundled
            | {"path": f"bundled/{dataset_id}.json", "version": "2026-10-24", "entries": 3},
        )
        for dataset_id in ("example-targets", "other-targets")
    )
    all_manifests = existing + manifests
    for module in (
        registry,
        packs,
        preferences,
        dataset_packs,
    ):
        monkeypatch.setattr(module, "list_datasets", lambda: all_manifests)
    monkeypatch.setattr("katanki.stats.sources.list_datasets", lambda: all_manifests)
    monkeypatch.setattr("katanki.dictionaries.manager.list_datasets", lambda: all_manifests)
    monkeypatch.setattr(updates, "USER_DATA", tmp_path / "installed")
    return manifests


def test_manifest_accepts_target_format_with_shared_license_and_bundle_contract(tmp_path):
    manifest_path = Path(__file__).parents[1] / "src/katanki/dictionaries/manifests/kanjidic2.json"
    raw = json.loads(manifest_path.read_text())
    raw.update(
        id="example-targets",
        format="target_lists_json",
        capabilities=["target_lists"],
        compression=["none"],
    )
    raw["bundled"]["path"] = "bundled/example-targets.json"
    path = tmp_path / "targets.json"
    path.write_text(json.dumps(raw))
    assert registry.read_manifest(path).capabilities == ("target_lists",)
    for change in ({"capabilities": ["kanji"]}, {"compression": ["gzip"]}):
        path.write_text(json.dumps(raw | change))
        with pytest.raises(ValueError):
            registry.read_manifest(path)


def test_two_target_packs_install_and_load_together_without_singleton_conflict(
    target_manifests, monkeypatch
):
    responses = {}
    for manifest in target_manifests:
        release, data, _ = target_pack(manifest)
        responses[release["url"]] = data
        monkeypatch.setattr(updates, "download", Mock(side_effect=lambda url, **kw: responses[url]))
        updates.install(manifest, release)
    network = Mock(side_effect=AssertionError("Offline load attempted network access"))
    monkeypatch.setattr(updates, "download", network)
    choices = (DictionaryChoice("kanjidic2", "disabled"),)
    targets = load_target_registry(choices=choices)
    assert len(targets.lists) == 2
    assert targets.targets(tuple((target.id, None) for target in targets.lists)) == (
        "日",
        "月",
        "火",
    )
    assert all(target.version == "2026-10-25" for target in targets.lists)
    assert all(target.source.authority == "unofficial" for target in targets.lists)
    selected = preferences.dictionary_sources(choices, capability="target_lists")
    assert all(path.is_relative_to(updates.USER_DATA) for path in selected.values())
    with DictionaryManager(selected) as dictionaries:
        assert dictionaries.status() == ()
    target_override = DictionaryChoice(target_manifests[0].id, "local", "/missing/list.json")
    assert target_manifests[0].id not in preferences.dictionary_sources((target_override,))
    details = preferences.check_dictionary(DictionaryChoice(target_manifests[0].id))
    assert "3 unique kanji" in details and "SHA-256" in details
    network.assert_not_called()


@pytest.mark.parametrize(
    "change",
    [
        lambda raw: raw.update(version="wrong-version"),
        lambda raw: raw["source"].update(url=None),
        lambda raw: raw["source"].update(sha256=None),
        lambda raw: raw["source"].update(authority="user"),
        lambda raw: raw["groups"][0]["characters"].append("日"),
        lambda raw: raw["groups"][0]["characters"].append("水"),
        lambda raw: raw["groups"][0]["characters"].append("あ"),
    ],
)
def test_invalid_target_update_does_not_activate(target_manifests, monkeypatch, change):
    manifest = target_manifests[0]
    release, data, _ = target_pack(manifest, change=change)
    monkeypatch.setattr(updates, "download", Mock(return_value=data))
    with pytest.raises(ValueError):
        updates.install(manifest, release)
    assert updates.installed(manifest) is None
    assert not (updates.USER_DATA / "active.json").exists()


def test_bad_update_preserves_existing_targets_and_corruption_falls_back(
    target_manifests, monkeypatch
):
    manifest = target_manifests[0]
    release, data, _ = target_pack(manifest)
    monkeypatch.setattr(updates, "download", Mock(return_value=data))
    updates.install(manifest, release)
    before = updates.default_source(manifest)
    _, bad_data, _ = target_pack(manifest, version="2026-10-26")
    # The advertised checksum is intentionally wrong.
    newer, _, _ = target_pack(manifest, version="2026-10-26")
    monkeypatch.setattr(updates, "download", Mock(return_value=bad_data + b"damage"))
    with pytest.raises(ValueError, match="SHA-256"):
        updates.install(manifest, newer)
    assert updates.default_source(manifest) == before
    assert parse_target_list(before.read_bytes()).target_list.characters() == ("日", "月", "火")
    before.write_bytes(b"corrupt")
    assert updates.default_source(manifest) == registry.bundled_path(manifest.bundled["path"])


def test_target_baseline_uses_same_locked_pack_restore_and_offline_cache(
    target_manifests, tmp_path, monkeypatch
):
    manifest = target_manifests[0]
    release, data, metadata = target_pack(manifest)
    manifest = replace(manifest, bundled=metadata["bundled"])
    bundled = tmp_path / "dictionaries/bundled"
    bundled.mkdir(parents=True)
    lock = tmp_path / "lock.json"
    lock.write_text(json.dumps({"schema_version": 1, "datasets": {manifest.id: release}}))
    monkeypatch.setattr(dataset_packs, "BUNDLED", bundled)
    monkeypatch.setattr(dataset_packs, "CACHE", tmp_path / "cache")
    monkeypatch.setattr(dataset_packs, "LOCK", lock)
    monkeypatch.setattr(dataset_packs, "list_datasets", lambda: (manifest,))
    monkeypatch.setattr(dataset_packs, "download", Mock(return_value=data))
    dataset_packs.restore()
    first = (bundled / f"{manifest.id}.json").read_bytes()
    monkeypatch.setattr(dataset_packs, "download", Mock(side_effect=AssertionError("Network used")))
    dataset_packs.restore(offline=True)
    assert (bundled / f"{manifest.id}.json").read_bytes() == first


def test_small_target_release_preparation_and_dictionary_refresh_preserve_list(
    target_manifests, tmp_path, monkeypatch
):
    manifest = target_manifests[0]
    release, data, metadata = target_pack(manifest)
    root = tmp_path / "dictionaries"
    root.mkdir()
    packs.unpack(data, manifest.id, release, root)
    bundled = root / "bundled"
    (bundled / "SOURCES.json").write_text('{"resources": {}}\n')
    (root / "manifests").mkdir()
    (root / "manifests" / f"{manifest.id}.json").write_text("{}")
    manifest = replace(manifest, bundled=metadata["bundled"])
    # The existing dictionary asset validator is tested separately; this fixture
    # contains a target baseline only, with no KANJIDIC/KanjiVG/Jitendex payloads.
    monkeypatch.setattr("scripts.build_addon.verify_bundled_assets", lambda source: None)
    monkeypatch.setattr(dataset_packs, "list_datasets", lambda: (manifest,))
    monkeypatch.setattr(dataset_packs, "BUNDLED", bundled)
    monkeypatch.setattr(dataset_packs, "CACHE", tmp_path / "cache")
    output = tmp_path / "release"
    catalog = dataset_packs.prepare("datasets-synthetic-targets", output)
    assert set(catalog["datasets"]) == {manifest.id}
    assert (output / f"{manifest.id}.zip").is_file()
    assert (output / "review" / f"{manifest.id}.json").is_file()
    packs.unpack(
        (output / f"{manifest.id}.zip").read_bytes(),
        manifest.id,
        catalog["datasets"][manifest.id],
        tmp_path / "roundtrip",
    )
    original_path = registry.bundled_path
    monkeypatch.setattr(
        registry,
        "bundled_path",
        lambda name, root=None: original_path(name, root or bundled.parent),
    )
    monkeypatch.setattr(bundle_datasets, "list_datasets", lambda: (manifest,))
    monkeypatch.setattr(bundle_datasets, "BUNDLED", bundled)
    stage = tmp_path / "new-bundle"
    stage.mkdir()
    # A newly prepared shared notice must not be overwritten by an older pack.
    (stage / "NOTICE.txt").write_text("New shared notice")
    assert bundle_datasets.preserve_target_datasets(stage) == {manifest.id: manifest.bundled}
    assert (stage / f"{manifest.id}.json").read_bytes() == (
        bundled / f"{manifest.id}.json"
    ).read_bytes()
    assert (stage / "NOTICE.txt").read_text() == "New shared notice"


def test_dictionary_update_and_disable_do_not_change_bundled_targets(tmp_path, monkeypatch):
    monkeypatch.setattr(updates, "USER_DATA", tmp_path / "installed")
    before = load_target_registry().lists
    manifest, release, data = candidate()
    monkeypatch.setattr(updates, "download", Mock(return_value=data))
    updates.install(manifest, release)
    assert load_target_registry().lists == before
    assert (
        load_target_registry(choices=(DictionaryChoice("kanjidic2", "disabled"),)).lists == before
    )
    assert (
        load_target_registry(
            choices=(
                DictionaryChoice("school-grades", "disabled"),
                DictionaryChoice("joyo", "disabled"),
            )
        ).lists
        == ()
    )


def test_reviewed_local_baseline_restores_without_a_published_release(
    target_manifests, tmp_path, monkeypatch
):
    dictionary, release, data = candidate()
    with ZipFile(io.BytesIO(data)) as archive:
        dictionary = replace(dictionary, bundled=json.loads(archive.read("PACK.json"))["bundled"])
    target = target_manifests[0]
    _, target_data, metadata = target_pack(target)
    target = replace(target, bundled=metadata["bundled"])
    with ZipFile(io.BytesIO(target_data)) as archive:
        payload = archive.read(target.bundled["path"])
    root = tmp_path / "repo"
    seed = root / f"dist/targets/{target.id}.json"
    seed.parent.mkdir(parents=True)
    seed.write_bytes(payload)
    lock = root / "datasets/bundled-lock.json"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "datasets": {dictionary.id: release},
                "local_datasets": {
                    target.id: {
                        "path": seed.relative_to(root).as_posix(),
                        "sha256": sha256(payload).hexdigest(),
                    }
                },
            }
        )
    )
    bundled = root / "src/katanki/dictionaries/bundled"
    bundled.mkdir(parents=True)
    monkeypatch.setattr(dataset_packs, "ROOT", root)
    monkeypatch.setattr(dataset_packs, "BUNDLED", bundled)
    monkeypatch.setattr(dataset_packs, "LOCK", lock)
    monkeypatch.setattr(dataset_packs, "CACHE", root / "data/packs")
    monkeypatch.setattr(dataset_packs, "list_datasets", lambda: (dictionary, target))
    monkeypatch.setattr(dataset_packs, "download", Mock(return_value=data))
    dataset_packs.restore()
    assert (bundled / f"{target.id}.json").read_bytes() == payload
    monkeypatch.setattr(dataset_packs, "download", Mock(side_effect=AssertionError("Network used")))
    dataset_packs.restore(offline=True)
    seed.write_bytes(payload + b"tampered")
    with pytest.raises(ValueError, match="checksum mismatch"):
        dataset_packs.restore(offline=True)
    assert (bundled / f"{target.id}.json").read_bytes() == payload
