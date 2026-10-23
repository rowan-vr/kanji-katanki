"""Conflict detection and refresh planning remain read-only until application."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from katanki.anki import example_refresh as refresh
from katanki.common.models import DiscoveryReport, KanjiEntry, ScanResult
from katanki.config import CardSettings, RefreshSettings, Settings
from katanki.generation.cards import CardContent, note_type_spec
from katanki.generation.examples import STATE_FIELD
from katanki.generation.planner import Identity


class Note(dict):
    def __init__(self, nid, identity, fields):
        super().__init__(fields)
        self.id, self.identity = nid, identity

    def note_type(self):
        return {
            "katanki_note_type": self.identity.note_type,
            "flds": [{"name": field} for field in note_type_spec(self.identity.note_type).fields],
            "tmpls": [{"qfmt": "custom", "afmt": "custom"}],
        }


@pytest.fixture
def setup(monkeypatch):
    notes = {}
    collection = Mock()

    def get_note(nid):
        note = notes[nid]
        return Note(nid, note.identity, dict(note))

    collection.get_note.side_effect = get_note
    collection.update_note.side_effect = lambda note: notes.update({note.id: note})
    monkeypatch.setattr(
        refresh,
        "owned_identities",
        lambda col, note_type: {
            note.identity: (nid,)
            for nid, note in notes.items()
            if note.identity.note_type == note_type
        },
    )
    manager = Mock()
    manager.__enter__ = Mock(return_value=manager)
    manager.__exit__ = Mock(return_value=False)
    manager.lookup_kanji.side_effect = lambda char: KanjiEntry(char, (), (), ("time",))
    monkeypatch.setattr(refresh, "DictionaryManager", lambda *args: manager)
    monkeypatch.setattr(refresh, "dictionary_sources", lambda *args: {})
    # Host-only no-op OpChanges, mirroring other pure tests at the Anki boundary.
    import sys

    monkeypatch.setitem(sys.modules, "anki.collection", SimpleNamespace(OpChanges=lambda: "noop"))
    return collection, notes


def report(words=("時計",)):
    return DiscoveryReport(
        ScanResult(1, ("時",), words), (KanjiEntry("時", (), (), ("time",)),), (), (), True, ()
    )


def add(notes, nid=1, mode="recognition", legacy=False):
    identity = Identity(f"kanji-{mode}", "時")
    content = CardContent(
        identity,
        "時",
        ("time",),
        prompt="time\n\n__間",
        examples=("時間",),
        discovered_examples=("時間",),
    )
    fields = content.fields()
    if legacy:
        fields.pop(STATE_FIELD)
    notes[nid] = Note(nid, identity, fields)
    return notes[nid]


def test_source_change_updates_managed_fields_and_keeps_user_examples(setup):
    collection, notes = setup
    note = add(notes)
    note["UserExamples"] = "My example"
    before = dict(note)
    plan = refresh.plan_example_refresh(collection, report(), Settings())
    assert dict(notes[1]) == before  # Planning never writes.
    assert len(plan.updates) == 1
    assert not plan.updates[0].migration
    result = refresh.apply_example_refresh(collection, plan)
    assert result.updated == 1
    assert "時計" in notes[1]["VocabExamples"] and "時間" not in notes[1]["VocabExamples"]
    assert notes[1]["UserExamples"] == "My example"
    assert not refresh.plan_example_refresh(collection, report(), Settings()).updates


def test_manual_edits_and_invalid_baselines_are_preserved(setup):
    collection, notes = setup
    note = add(notes)
    note["VocabExamples"] = "My managed edit"
    plan = refresh.plan_example_refresh(collection, report(), Settings())
    assert not plan.updates and "manually edited" in plan.conflicts[0]
    note[STATE_FIELD] = "damaged"
    plan = refresh.plan_example_refresh(collection, report(), Settings())
    assert not plan.updates and "invalid" in plan.conflicts[0]


def test_both_refresh_switches_are_respected(setup):
    collection, notes = setup
    add(notes)
    for settings in (
        Settings(refresh=RefreshSettings(update_examples=False)),
        Settings(cards=(CardSettings(auto_refresh=False), CardSettings(), CardSettings())),
    ):
        assert not refresh.plan_example_refresh(collection, report(), settings).updates


def test_legacy_migration_requires_explicit_opt_in(setup):
    collection, notes = setup
    add(notes, legacy=True)
    plan = refresh.plan_example_refresh(collection, report(), Settings())
    assert plan.updates[0].migration
    assert refresh.apply_example_refresh(collection, plan).updated == 0
    assert refresh.apply_example_refresh(collection, plan, migrate=True).updated == 1
    assert STATE_FIELD in notes[1]


def test_stale_snapshot_is_not_written(setup):
    collection, notes = setup
    add(notes)
    plan = refresh.plan_example_refresh(collection, report(), Settings())
    notes[1]["UserExamples"] = "Edited while preview open"
    result = refresh.apply_example_refresh(collection, plan)
    assert result.updated == 0 and "changed since preview" in result.conflicts[0]


def test_source_removal_clears_recognition_but_keeps_production_clues(setup):
    collection, notes = setup
    add(notes)
    add(notes, nid=2, mode="production")
    empty = replace(report(()), entries=(), scan=ScanResult(0, ()))
    plan = refresh.plan_example_refresh(collection, empty, Settings())
    assert len(plan.updates) == 1
    assert dict(plan.updates[0].after)["VocabExamples"] == ""
    assert "empty production clues" in plan.conflicts[0]


def test_production_uses_user_first_and_masks_every_target(setup):
    collection, notes = setup
    note = add(notes, mode="production")
    note["UserExamples"] = "<div>時時</div><div>時計</div>"
    settings = Settings(cards=(CardSettings(), CardSettings(example_limit=1), CardSettings()))
    plan = refresh.plan_example_refresh(collection, report(), settings)
    assert dict(plan.updates[0].after)["Prompt"] == "time<br><br>____"
    assert "時計" in dict(plan.updates[0].after)["VocabExamples"]


def test_new_production_collision_between_plan_and_apply_is_preserved(setup):
    collection, notes = setup
    add(notes, mode="production")
    plan = refresh.plan_example_refresh(collection, report(), Settings())
    identity = Identity("kanji-production", "間")
    content = CardContent(identity, "間", prompt="time\n\n__計")
    notes[2] = Note(2, identity, content.fields())
    result = refresh.apply_example_refresh(collection, plan)
    assert result.updated == 0 and "conflict" in result.conflicts[0]


def test_duplicate_visible_production_clues_are_blocked_during_planning(setup):
    collection, notes = setup
    add(notes, mode="production")
    identity = Identity("kanji-production", "間")
    content = CardContent(identity, "間", prompt="old distinct")
    notes[2] = Note(2, identity, content.fields())
    # Both become "time / ____" after masking and limiting.
    proposed = replace(
        report(("時時", "間間")),
        entries=(
            KanjiEntry("時", (), (), ("time",)),
            KanjiEntry("間", (), (), ("time",)),
        ),
    )
    notes[2]["Meanings"] = "time"
    plan = refresh.plan_example_refresh(collection, proposed, Settings())
    assert not plan.updates
    assert len(plan.conflicts) == 2


def test_parts_examples_clear_even_after_all_source_kanji_disappear(setup):
    collection, notes = setup
    identity = Identity("primitive-recognition", "日")
    content = CardContent(identity, "日", examples=("時",))
    notes[1] = Note(1, identity, content.fields())
    plan = refresh.plan_example_refresh(
        collection, replace(report(()), entries=(), strokes=()), Settings()
    )
    assert len(plan.updates) == 1
    assert dict(plan.updates[0].after)["VocabExamples"] == ""


def test_changed_settings_and_sources_invalidate_refresh_result(setup, monkeypatch):
    from katanki.anki import refresh as workflow

    collection, notes = setup
    add(notes)
    settings = Settings()
    result = SimpleNamespace(
        report=report(), examples=refresh.plan_example_refresh(collection, report(), settings)
    )
    monkeypatch.setattr(
        workflow,
        "load_settings",
        lambda col: replace(settings, refresh=RefreshSettings(update_examples=False)),
    )
    outcome = workflow.apply_refresh_examples(collection, result, settings)
    assert outcome.updated == 0 and "Settings changed" in outcome.conflicts[0]
    monkeypatch.setattr(workflow, "load_settings", lambda col: settings)
    monkeypatch.setattr(workflow, "resolve_sources", lambda *args: ())
    monkeypatch.setattr(workflow, "selected_notes", lambda *args: ())
    outcome = workflow.apply_refresh_examples(collection, result, settings)
    assert outcome.updated == 0 and "Source vocabulary changed" in outcome.conflicts[0]
