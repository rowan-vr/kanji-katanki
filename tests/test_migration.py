"""Migration preflight must reject ambiguity before touching a collection."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from katanki.anki import migration
from katanki.common.models import DiscoveryReport, KanjiEntry, ScanResult
from katanki.config import Settings
from katanki.generation.planner import Identity


@pytest.fixture
def source():
    return migration.MigrationSource("recognition", 1, 10, "Kanji")


@pytest.fixture
def collection():
    model = {
        "id": 10,
        "name": "Foreign cards",
        "type": 0,
        "flds": [{"name": "Kanji"}],
        "tmpls": [{"name": "Recognition", "ord": 0}],
    }
    col = Mock()
    col.models.get.return_value = model
    col.models.all.return_value = [model]
    col.decks.get.return_value = {"id": 1}
    col.find_cards.return_value = [100]
    card = SimpleNamespace(id=100, nid=200, did=1, odid=0, ord=0)
    col.get_card.return_value = card
    note = Mock()
    note.__getitem__ = Mock(return_value="<ruby>景<rt>けい</rt></ruby>")
    col.get_note.return_value = note
    return col


def test_scan_selects_exact_deck_and_visible_single_kanji_regardless_of_template(
    collection, source
):
    candidates, warnings = migration._scan(collection, (source,))
    assert candidates[0][2] == Identity("kanji-recognition", "景")
    assert warnings == []
    collection.get_card.return_value.ord = 1
    assert migration._scan(collection, (source,))[0][0][2] == Identity("kanji-recognition", "景")
    collection.get_card.return_value.ord = 0
    collection.get_card.return_value.did = 2
    assert migration._scan(collection, (source,)) == ([], [])


@pytest.mark.parametrize("value", ["日本", "景 abc", "", "けい", "景景"])
def test_ambiguous_field_never_guesses_a_character(collection, source, value):
    collection.get_note.return_value.__getitem__.return_value = value
    candidates, warnings = migration._scan(collection, (source,))
    assert not candidates and "exactly one kanji" in warnings[0]


def test_filtered_card_is_skipped_not_rescheduled(collection, source):
    card = collection.get_card.return_value
    card.did, card.odid = 99, 1
    candidates, warnings = migration._scan(collection, (source,))
    assert not candidates and "filtered deck" in warnings[0]
    collection.update_card.assert_not_called()


def test_one_card_cannot_supply_two_categories(collection, source):
    with pytest.raises(ValueError, match="multiple categories"):
        migration._scan(collection, (source, replace(source, category="production")))


@pytest.mark.parametrize(
    "change, message",
    [
        ({"type": 1}, "Cloze"),
        ({migration.MODEL_MARKER: "kanji-recognition"}, "not owned"),
        ({"flds": []}, "field"),
    ],
)
def test_invalid_note_types_rejected(collection, source, change, message):
    collection.models.get.return_value.update(change)
    with pytest.raises(ValueError, match=message):
        migration._scan(collection, (source,))


def test_no_categories_rejected(collection):
    with pytest.raises(ValueError, match="source deck"):
        migration._scan(collection, ())


def test_missing_deck_rejected(collection, source):
    collection.decks.get.return_value = None
    with pytest.raises(ValueError, match="deck"):
        migration._scan(collection, (source,))


@pytest.mark.parametrize("duplicate_source", [True, False])
def test_duplicate_source_or_existing_identity_skipped_after_classification(
    collection,
    source,
    monkeypatch,
    duplicate_source,
):
    identity = Identity("kanji-recognition", "景")
    note = collection.get_note.return_value
    card = collection.get_card.return_value
    monkeypatch.setattr(
        migration,
        "_scan",
        lambda *_, **_kw: ([(card, note, identity)] * (2 if duplicate_source else 1), []),
    )
    monkeypatch.setattr(
        migration,
        "owned_identities",
        lambda *_args, **_kw: {} if duplicate_source else {identity: (500,)},
    )
    analyze = Mock(
        return_value=DiscoveryReport(
            ScanResult(0, ("景",)), (KanjiEntry("景", (), (), ("view",)),), (), (), True, ()
        )
    )
    monkeypatch.setattr(migration, "analyze_scan", analyze)
    plan = migration.prepare_migration(collection, (source,), settings=Settings())
    assert not plan.items
    assert all("duplicate" in warning for warning in plan.warnings)
    analyze.assert_called_once()


def test_missing_dictionary_content_skips_card(collection, source, monkeypatch):
    monkeypatch.setattr(migration, "owned_identities", lambda *_args, **_kw: {})
    monkeypatch.setattr(
        migration,
        "analyze_scan",
        lambda *_: DiscoveryReport(
            ScanResult(0, ("景",)), (), (), ("景",), False, (), ("No dictionary",)
        ),
    )
    monkeypatch.setattr(
        migration, "selected_words", lambda *_, **_kw: SimpleNamespace(lookup=lambda _: ())
    )
    plan = migration.prepare_migration(collection, (source,), settings=Settings())
    assert not plan.items
    assert "No dictionary" in plan.warnings
    assert "unavailable" in plan.warnings[-1]


def test_production_clue_collision_cannot_migrate(collection, source, monkeypatch):
    monkeypatch.setattr(migration, "owned_identities", lambda *_args, **_kw: {})
    monkeypatch.setattr(
        migration,
        "analyze_scan",
        lambda *_: DiscoveryReport(
            ScanResult(0, ("景",)), (KanjiEntry("景", (), (), ("view",)),), (), (), True, ()
        ),
    )
    monkeypatch.setattr(
        migration, "selected_words", lambda *_, **_kw: SimpleNamespace(lookup=lambda _: ())
    )
    monkeypatch.setattr(migration, "_validate_prompts", Mock(side_effect=ValueError("collision")))
    with pytest.raises(ValueError, match="collision"):
        migration.prepare_migration(
            collection, (replace(source, category="production"),), settings=Settings()
        )


@pytest.mark.parametrize("mode", ["recognition", "production"])
@pytest.mark.parametrize("key", ["⺡", "亻", "日"])
def test_kanji_and_parts_detected_from_character_in_both_directions(
    collection, source, monkeypatch, mode, key
):
    from katanki.common.models import ComponentEntry, StrokeEntry

    part = ComponentEntry(key, key, b"<svg/>")
    report = DiscoveryReport(
        ScanResult(0, (key,)),
        (KanjiEntry(key, (), (), ("water radical",)),) if key == "日" else (),
        (StrokeEntry("景", b"<svg/>", (key,), (part,)),),
        (),
        True,
        (),
    )
    monkeypatch.setattr(migration, "analyze_scan", lambda *_: report)
    manager = Mock()
    manager.lookup_strokes.return_value = None
    manager.card_attribution.return_value = ()
    context = Mock()
    context.__enter__ = Mock(return_value=manager)
    context.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(migration, "DictionaryManager", lambda *_: context)
    monkeypatch.setattr(migration, "owned_identities", lambda *_args, **_kw: {})
    monkeypatch.setattr(
        migration, "selected_words", lambda *_, **_kw: SimpleNamespace(lookup=lambda _: ())
    )
    note = collection.get_note.return_value
    note.id, note.mid, note.guid, note.tags = 200, 10, "source", ["old"]
    fields = {"Kanji": key, "Meaning": "water radical"}
    note.__getitem__.side_effect = fields.__getitem__
    note.keys.return_value = fields.keys()
    note.items.return_value = fields.items()
    collection.get_card.return_value._to_backend_card = Mock()
    backend = collection.get_card.return_value._to_backend_card.return_value
    backend.SerializeToString.return_value = b"card"
    collection.db.all.return_value = []
    plan = migration.prepare_migration(
        collection, (replace(source, category=mode),), settings=Settings()
    )
    assert len(plan.items) == 1, plan.warnings
    kind = "kanji" if key == "日" else "primitive"
    assert plan.items[0].identity == Identity(f"{kind}-{mode}", key)
    assert plan.items[0].content.svg == (b"" if key == "日" else b"<svg/>")
    assert plan.items[0].content.prompt == ("water radical" if mode == "production" else "")


def test_old_parts_category_is_not_a_source_mapping(collection, source):
    with pytest.raises(ValueError, match="category"):
        migration._scan(collection, (replace(source, category="parts"),))


@pytest.fixture
def conversion(monkeypatch):
    """A collection double retaining card ownership, scheduling and history."""
    import sys

    from katanki.generation.cards import CardContent, note_type_spec

    monkeypatch.setitem(sys.modules, "anki.collection", SimpleNamespace(OpChanges=lambda: "noop"))
    identity = Identity("kanji-recognition", "景")
    model = {
        "id": 20,
        migration.MODEL_MARKER: identity.note_type,
        "tmpls": [{"ord": 0}],
        "flds": [{"name": name} for name in note_type_spec(identity.note_type).fields],
    }
    card = SimpleNamespace(id=100, nid=200, ord=1, did=7)
    backend = Mock()
    backend.SerializeToString.return_value = b"original-card"
    card._to_backend_card = Mock(return_value=backend)
    old = Mock(id=200, guid="source", mid=10, tags=["user"])
    old.items.return_value = [("Kanji", "景")]
    old.cards.return_value = []

    class NewNote(dict):
        id = 300
        tags = []

        def cards(self):
            return [SimpleNamespace(id=101)]

    new = NewNote()
    col = Mock()
    col.models.all.return_value = [model]
    col.get_card.return_value = card
    col.get_note.return_value = old
    col.new_note.return_value = new
    col.db.all.return_value = [(1, 100, 2)]
    col.add_custom_undo_entry.return_value = 99
    settings = Settings()
    monkeypatch.setattr(migration, "load_settings", lambda _: settings)
    monkeypatch.setattr(migration, "owned_identities", lambda *_, **__: {})
    monkeypatch.setattr(migration, "_validate_prompts", Mock())
    monkeypatch.setattr(migration, "_scan", lambda *_, **__: ([(card, old, identity)], []))
    item = migration.MigrationItem(
        card.id,
        old.id,
        identity,
        CardContent(identity, "景"),
        b"original-card",
        migration._note_snapshot(old),
        ((1, 100, 2),),
    )
    plan = migration.MigrationPlan((), (item,), (), settings, migration._models_snapshot(col))
    return SimpleNamespace(col=col, card=card, old=old, new=new, model=model, plan=plan)


def test_conversion_transfers_original_card_and_preserves_history(conversion):
    fixture = conversion
    progress = Mock()
    migration.apply_migration(fixture.col, fixture.plan, progress=progress)
    assert (fixture.card.id, fixture.card.nid, fixture.card.ord, fixture.card.did) == (
        100,
        300,
        0,
        7,
    )
    assert fixture.new.tags == ["user"]
    assert fixture.new["Character"] == "景"
    fixture.col.update_card.assert_called_once_with(fixture.card)
    fixture.col.remove_cards_and_orphaned_notes.assert_called_once_with([101])
    fixture.col.remove_notes.assert_called_once_with([200])
    fixture.col.db.execute.assert_not_called()
    fixture.col.undo.assert_not_called()
    assert "Verifying" in progress.call_args_list[-2].args[0]


def test_conversion_keeps_source_note_with_unmapped_sibling(conversion):
    conversion.old.cards.return_value = [SimpleNamespace(id=102)]
    migration.apply_migration(conversion.col, conversion.plan)
    conversion.col.remove_notes.assert_not_called()


@pytest.mark.parametrize("change", ["settings", "models", "card", "note", "history", "ownership"])
def test_conversion_rejects_stale_approval_before_writes(conversion, monkeypatch, change):
    fixture = conversion
    if change == "settings":
        monkeypatch.setattr(migration, "load_settings", lambda _: Settings(destination_deck_id=3))
    elif change == "models":
        fixture.model["name"] = "Changed"
    elif change == "card":
        fixture.card._to_backend_card.return_value.SerializeToString.return_value = b"changed"
    elif change == "note":
        fixture.old.tags.append("edited")
    elif change == "history":
        fixture.col.db.all.return_value = []
    else:
        monkeypatch.setattr(
            migration, "owned_identities", lambda *_, **__: {fixture.plan.items[0].identity: (99,)}
        )
    with pytest.raises(ValueError, match="changed"):
        migration.apply_migration(fixture.col, fixture.plan)
    fixture.col.add_custom_undo_entry.assert_not_called()
    fixture.col.update_card.assert_not_called()


@pytest.mark.parametrize("problem", ["duplicates", "templates", "fields"])
def test_conversion_rejects_invalid_target_models(conversion, problem):
    fixture = conversion
    if problem == "duplicates":
        fixture.col.models.all.return_value.append(dict(fixture.model))
    elif problem == "templates":
        fixture.model["tmpls"] = [{"ord": 1}]
    else:
        fixture.model["flds"] = []
    plan = replace(fixture.plan, models_snapshot=migration._models_snapshot(fixture.col))
    with pytest.raises(ValueError):
        migration.apply_migration(fixture.col, plan)
    fixture.col.add_custom_undo_entry.assert_not_called()


def test_conversion_removes_legacy_archive_field_under_undo(conversion):
    fixture = conversion
    legacy = {"name": "MigrationSource"}
    fixture.model["flds"].append(legacy)
    plan = replace(fixture.plan, models_snapshot=migration._models_snapshot(fixture.col))
    migration.apply_migration(fixture.col, plan)
    fixture.col.models.remove_field.assert_called_once_with(fixture.model, legacy)
    fixture.col.models.update_dict.assert_called_once_with(fixture.model)


def test_conversion_creates_target_model_when_missing(conversion):
    fixture = conversion
    fixture.col.models.all.return_value = []
    fixture.col.models.new.return_value = {}
    fixture.col.models.new_template.return_value = {}
    fixture.col.models.add_dict.return_value = SimpleNamespace(id=20)
    fixture.col.models.get.return_value = fixture.model
    plan = replace(fixture.plan, models_snapshot=migration._models_snapshot(fixture.col))
    migration.apply_migration(fixture.col, plan)
    fixture.col.models.add_dict.assert_called_once()
    assert fixture.col.models.add_field.call_count == len(fixture.model["flds"])
    assert fixture.card.nid == fixture.new.id


@pytest.mark.parametrize("failure", ["transfer", "schedule", "history"])
def test_conversion_rolls_back_after_partial_writes(conversion, monkeypatch, failure):
    fixture = conversion
    if failure == "transfer":
        fixture.col.update_card.side_effect = RuntimeError("transfer failed")
    elif failure == "schedule":
        monkeypatch.setattr(migration, "_schedule", Mock(side_effect=[b"before", b"after"]))
    else:
        fixture.col.db.all.side_effect = [[(1, 100, 2)], []]
    with pytest.raises(RuntimeError):
        migration.apply_migration(fixture.col, fixture.plan)
    fixture.col.undo.assert_called_once()
    fixture.col.merge_undo_entries.assert_called_with(99)


def test_empty_conversion_is_noop(conversion):
    result = migration.apply_migration(conversion.col, replace(conversion.plan, items=()))
    assert result == "noop"
    conversion.col.add_custom_undo_entry.assert_not_called()
