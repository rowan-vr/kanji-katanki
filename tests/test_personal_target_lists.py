import json

import pytest

from katanki.anki.target_lists import PersonalTargetStore
from katanki.stats.targets import MAX_BYTES, read_target_list
from tests.test_target_lists import example_list


def source(tmp_path, raw=None):
    path = tmp_path / "import.json"
    path.write_text(json.dumps(raw or example_list()), encoding="utf-8")
    return path


def test_profile_isolation_roundtrip_and_safe_paths(tmp_path):
    store = PersonalTargetStore(tmp_path / "user_files", "../../profile/日本")
    other = PersonalTargetStore(tmp_path / "user_files", "other")
    assert store.load() == ()
    preview = store.preview(source(tmp_path))
    assert preview.existing is None
    assert preview.added == ("日", "月", "火")
    target = store.install(preview)
    assert store.load() == (target,)
    assert other.load() == ()
    assert store.directory.parent.parent == tmp_path / "user_files"
    output = tmp_path / "export.json"
    store.export(target.id, output)
    assert read_target_list(output).target_list == target
    store.remove(target.id)
    assert store.load() == ()
    with pytest.raises(ValueError, match="Unknown"):
        store.remove(target.id)


def test_replacement_preview_and_identical_noop(tmp_path):
    store = PersonalTargetStore(tmp_path / "user_files", "profile")
    path = source(tmp_path)
    store.install(store.preview(path))
    stored = next(store.directory.glob("*.json"))
    before = stored.stat().st_mtime_ns
    preview = store.preview(path)
    assert preview.unchanged
    store.install(preview)
    assert stored.stat().st_mtime_ns == before
    raw = example_list()
    raw["groups"] = [{"id": "new", "title": "New", "characters": ["水", "日"]}]
    preview = store.preview(source(tmp_path, raw))
    assert preview.added == ("水",)
    assert preview.removed == ("月", "火")
    with pytest.raises(ValueError, match="Explicit replacement"):
        store.install(preview)
    target = store.install(preview, replace=True)
    assert store.load() == (target,)
    with pytest.raises(ValueError, match="changed after preview"):
        store.install(preview, replace=True)


def test_reserved_invalid_and_oversized_imports_leave_store_untouched(tmp_path):
    store = PersonalTargetStore(tmp_path / "user_files", "profile")
    path = source(tmp_path)
    with pytest.raises(ValueError, match="reserved"):
        store.preview(path, reserved_ids=("user:course-1",))
    path.write_text('{"schema_version": 2}', encoding="utf-8")
    with pytest.raises(ValueError):
        store.preview(path)
    path.write_bytes(b" " * (MAX_BYTES + 1))
    with pytest.raises(ValueError, match="size limit"):
        store.preview(path)
    assert store.load() == ()
    assert not store.directory.exists()


def test_corrupt_storage_fails_visibly_and_preserves_file(tmp_path):
    store = PersonalTargetStore(tmp_path / "user_files", "profile")
    store.install(store.preview(source(tmp_path)))
    path = next(store.directory.glob("*.json"))
    path.write_bytes(b"broken")
    with pytest.raises(ValueError, match="Cannot load personal"):
        store.load()
    assert path.read_bytes() == b"broken"


def test_wrong_stored_filename_and_empty_profile_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="profile key"):
        PersonalTargetStore(tmp_path, "")
    store = PersonalTargetStore(tmp_path / "user_files", "profile")
    store.directory.mkdir(parents=True)
    (store.directory / "unexpected.json").write_text(json.dumps(example_list()), encoding="utf-8")
    with pytest.raises(ValueError, match="unexpected filename"):
        store.load()


def test_failed_atomic_replacement_preserves_existing_data(tmp_path, monkeypatch):
    store = PersonalTargetStore(tmp_path / "user_files", "profile")
    old = store.install(store.preview(source(tmp_path)))
    raw = example_list()
    raw["title"] = "Updated title"
    preview = store.preview(source(tmp_path, raw))

    def fail_replace(*args):
        raise OSError("simulated disk failure")

    monkeypatch.setattr("katanki.anki.target_lists.os.replace", fail_replace)
    with pytest.raises(OSError, match="disk failure"):
        store.install(preview, replace=True)
    assert store.load() == (old,)
    assert len(list(store.directory.iterdir())) == 1


def test_collection_helpers_isolate_profiles_without_creating_files(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from katanki.anki import target_lists

    monkeypatch.setattr(
        target_lists, "__file__", str(tmp_path / "addon" / "anki" / "target_lists.py")
    )
    first = SimpleNamespace(path=str(tmp_path / "profiles" / "First" / "collection.anki2"))
    second = SimpleNamespace(path=str(tmp_path / "profiles" / "Second" / "collection.anki2"))
    store = target_lists.store_for_collection(first)
    assert store.directory != target_lists.store_for_collection(second).directory
    assert (
        target_lists.get_personal_target_store(SimpleNamespace(col=first)).directory
        == store.directory
    )
    assert tmp_path / "addon" / "user_files" / "target_lists" in store.directory.parents
    assert not store.directory.exists()


def dashboard_fixture(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from katanki.anki import statistics
    from katanki.stats.targets import TargetRegistry, parse_target_list

    builtin = parse_target_list(json.dumps(example_list("builtin:course")).encode()).target_list
    monkeypatch.setattr(statistics, "load_settings", lambda _: SimpleNamespace(dictionaries=()))
    monkeypatch.setattr(
        statistics, "load_target_registry", lambda **kwargs: TargetRegistry((builtin,))
    )
    monkeypatch.setattr(statistics, "dictionary_sources", lambda *args, **kwargs: {})
    store = PersonalTargetStore(tmp_path / "user_files", "profile")
    monkeypatch.setattr(statistics, "store_for_collection", lambda _: store)
    # This collection exposes only read APIs; accidental note/card writes fail immediately.
    collection = SimpleNamespace(
        path=str(tmp_path / "profile" / "collection.anki2"),
        models=SimpleNamespace(all=lambda: []),
    )
    return statistics, collection, store, builtin


def test_dashboard_adds_personal_targets_without_collection_mutation(tmp_path, monkeypatch):
    statistics, collection, store, builtin = dashboard_fixture(tmp_path, monkeypatch)
    personal = store.install(store.preview(source(tmp_path)))
    registry, progress, _, warnings = statistics.dashboard_snapshot(collection)
    assert registry.lists == (builtin, personal)
    assert progress.cards == ()
    assert warnings == []
    assert store.load() == (personal,)


def test_dashboard_corrupt_personal_storage_preserves_builtin_targets(tmp_path, monkeypatch):
    statistics, collection, store, builtin = dashboard_fixture(tmp_path, monkeypatch)
    store.install(store.preview(source(tmp_path)))
    next(store.directory.glob("*.json")).write_bytes(b"corrupt")
    registry, _, _, warnings = statistics.dashboard_snapshot(collection)
    assert registry.lists == (builtin,)
    assert any("personal" in warning.lower() for warning in warnings)


def test_dashboard_personal_id_collision_warns_and_preserves_builtin(tmp_path, monkeypatch):
    statistics, collection, store, builtin = dashboard_fixture(tmp_path, monkeypatch)
    store.install(store.preview(source(tmp_path, example_list(builtin.id))))
    registry, _, _, warnings = statistics.dashboard_snapshot(collection)
    assert registry.lists == (builtin,)
    assert warnings
    assert builtin.id in " ".join(warnings)
