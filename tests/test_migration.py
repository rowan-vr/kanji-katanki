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
