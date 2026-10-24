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
        self.tags = []

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
        result = Note(nid, note.identity, dict(note))
        result.tags = list(note.tags)
        return result

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
    manager.lookup_strokes.return_value = None
    monkeypatch.setattr(
        refresh, "selected_words", lambda choices: SimpleNamespace(lookup=lambda key: ())
    )
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


@pytest.mark.parametrize("baseline", (None, "damaged"))
def test_managed_edits_are_overwritten_and_user_examples_preserved(setup, baseline):
    collection, notes = setup
    note = add(notes)
    note["VocabExamples"] = "My managed edit"
    note["UserExamples"] = "My custom example"
    if baseline is not None:
        note[STATE_FIELD] = baseline
    plan = refresh.plan_example_refresh(collection, report(), Settings())
    assert not plan.conflicts and not plan.updates[0].migration
    assert refresh.apply_example_refresh(collection, plan).updated == 1
    assert "時計" in notes[1]["VocabExamples"]
    assert notes[1]["UserExamples"] == "My custom example"
    assert not refresh.plan_example_refresh(collection, report(), Settings()).updates


def test_both_refresh_switches_are_respected(setup):
    collection, notes = setup
    add(notes)
    for settings in (
        Settings(refresh=RefreshSettings(update_examples=False)),
        Settings(cards=(CardSettings(auto_refresh=False), CardSettings(), CardSettings())),
    ):
        assert not refresh.plan_example_refresh(collection, report(), settings).updates


def test_legacy_tracking_is_replaced_without_review(setup):
    collection, notes = setup
    add(notes, legacy=True)
    plan = refresh.plan_example_refresh(collection, report(), Settings())
    assert not plan.updates[0].migration
    assert refresh.apply_example_refresh(collection, plan).updated == 1
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


def test_production_ignores_deferred_user_examples(setup):
    collection, notes = setup
    note = add(notes, mode="production")
    note["UserExamples"] = "<div>時時</div><div>時計</div>"
    settings = Settings(cards=(CardSettings(), CardSettings(example_limit=1), CardSettings()))
    plan = refresh.plan_example_refresh(collection, report(), settings)
    assert dict(plan.updates[0].after)["Prompt"] == "time<br><br>__計"
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


def test_dictionary_refresh_without_example_updates(setup):
    collection, notes = setup
    note = add(notes)
    note["Meanings"] = "old meaning"
    note["UserExamples"] = "keep this"
    settings = Settings(refresh=RefreshSettings(update_examples=False, update_dictionary_data=True))
    plan = refresh.plan_example_refresh(collection, report(), settings)
    assert len(plan.updates) == 1
    assert not plan.updates[0].migration
    refresh.apply_example_refresh(collection, plan)
    assert notes[1]["Meanings"] == "time"
    assert notes[1]["UserExamples"] == "keep this"
    assert notes[1]["VocabExamples"] == note["VocabExamples"]
    assert not refresh.plan_example_refresh(collection, report(), settings).updates


def test_tag_refresh_preserves_tags_and_rejects_stale_tags(setup):
    from katanki.config import GenerationSettings

    collection, notes = setup
    note = add(notes)
    note.tags = ["personal"]
    settings = Settings(
        refresh=RefreshSettings(update_examples=False, update_source_tags=True),
        generation=(GenerationSettings(default_tags=("generated",)),) * 3,
    )
    plan = refresh.plan_example_refresh(collection, report(), settings)
    assert len(plan.updates) == 1
    note.tags.append("later")
    assert refresh.apply_example_refresh(collection, plan).updated == 0
    plan = refresh.plan_example_refresh(collection, report(), settings)
    assert refresh.apply_example_refresh(collection, plan).updated == 1
    assert notes[1].tags == ["personal", "later", "generated"]
    assert not refresh.plan_example_refresh(collection, report(), settings).updates


def test_combined_dictionary_and_example_refresh_keeps_valid_baseline(setup):
    collection, notes = setup
    note = add(notes)
    note["Readings"] = "old"
    settings = Settings(refresh=RefreshSettings(update_dictionary_data=True))
    plan = refresh.plan_example_refresh(collection, report(), settings)
    assert refresh.apply_example_refresh(collection, plan).updated == 1
    assert notes[1]["Readings"] == ""
    assert "時計" in notes[1]["VocabExamples"]
    assert not refresh.plan_example_refresh(collection, report(), settings).updates


def test_review_stage_changes_refresh_only_saved_status_and_preserve_user_edits(setup):
    collection, notes = setup
    note = add(notes)
    note["UserExamples"] = "<div>My own example</div>"
    discovery = replace(
        report(("時間",)),
        scan=ScanResult(1, ("時",), ("時間",), vocabulary_statuses=(("時間", "learned"),)),
    )
    plan = refresh.plan_example_refresh(collection, discovery, Settings())
    assert len(plan.updates) == 1
    assert 'data-status="learned"' in dict(plan.updates[0].after)["VocabExamples"]
    assert refresh.apply_example_refresh(collection, plan).updated == 1
    assert notes[1]["UserExamples"] == "<div>My own example</div>"
    assert not refresh.plan_example_refresh(collection, discovery, Settings()).updates
    # A subsequent source removal clears its saved status without removing cards.
    plan = refresh.plan_example_refresh(collection, report(()), Settings())
    assert dict(plan.updates[0].after)["VocabExamples"] == ""
    assert len(notes) == 1


def test_stock_layout_upgrade_is_planned_even_when_example_values_are_unchanged(setup, monkeypatch):
    from katanki.generation import legacy_cards

    collection, notes = setup
    add(notes)
    original = Note.note_type

    def old_type(self):
        model = original(self)
        model["tmpls"] = [
            {"qfmt": legacy_cards.front(self.identity.note_type), "afmt": legacy_cards.BACK}
        ]
        model["css"] = legacy_cards.STYLES[0]
        return model

    monkeypatch.setattr(Note, "note_type", old_type)
    plan = refresh.plan_example_refresh(collection, report(("時間",)), Settings())
    assert len(plan.updates) == 1
    assert not plan.updates[0].migration
    # Planning never persists templates or notes.
    collection.models.update_dict.assert_not_called()
    assert refresh.apply_example_refresh(collection, plan).updated == 1
    updated = collection.models.update_dict.call_args.args[0]
    assert updated["tmpls"][0]["afmt"] == note_type_spec("kanji-recognition").back


@pytest.mark.parametrize("mode", ("recognition", "production"))
def test_refresh_keeps_all_words_even_when_front_limit_is_one(setup, mode):
    from katanki.generation.examples import lines

    collection, notes = setup
    add(notes, mode=mode)
    words = (
        "時間",
        "時計",
        "時代",
        "時期",
        "時刻",
        "時差",
        "時速",
        "時給",
        "当時",
        "同時",
        "一時",
        "時々",
        "何時",
        "時点",
        "定時",
        "臨時",
    )
    options = CardSettings(example_limit=1)
    settings = Settings(cards=(options, options, options))
    discovery = replace(
        report(words),
        scan=ScanResult(
            len(words),
            ("時",),
            words,
            vocabulary_statuses=(
                ("時間", "learned"),
                ("時計", "relearning"),
                ("時代", "learning"),
                ("定時", "new"),
            ),
        ),
    )
    plan = refresh.plan_example_refresh(collection, discovery, settings)
    assert len(plan.updates) == 1
    after = dict(plan.updates[0].after)
    assert set(lines(after["VocabExamples"])) == set(words)
    for stage in ("learned", "relearning", "learning", "new"):
        assert f'data-status="{stage}"' in after["VocabExamples"]
    if mode == "production":
        assert len(lines(after["Prompt"])) == 2  # Meaning plus one front clue only.
    assert refresh.apply_example_refresh(collection, plan).updated == 1
    assert set(lines(notes[1]["VocabExamples"])) == set(words)
    assert not refresh.plan_example_refresh(collection, discovery, settings).updates


@pytest.mark.parametrize("mode", ("recognition", "production"))
def test_damaged_baseline_repairs_tracking_without_review_and_is_idempotent(setup, mode):
    import json

    collection, notes = setup
    note = add(notes, mode=mode)
    note["UserExamples"] = "<div>時々</div>"
    note[STATE_FIELD] = (
        '{"version": 1, "fields": {"VocabExamples": "<div data-source="x">時間</div>"}}'
    )
    before = dict(note)
    plan = refresh.plan_example_refresh(collection, report(), Settings())
    assert len(plan.updates) == 1 and not plan.updates[0].migration
    assert refresh.apply_example_refresh(collection, plan).updated == 1
    assert notes[1]["UserExamples"] == before["UserExamples"]
    assert json.loads(notes[1][STATE_FIELD])["version"] == 1
    assert "<" not in notes[1][STATE_FIELD]
    assert not refresh.plan_example_refresh(collection, report(), Settings()).updates


def test_valid_legacy_baseline_is_encoded_safely_without_manual_adoption(setup):
    import json

    collection, notes = setup
    note = add(notes)
    # Reproduce the valid raw-JSON format from older add-ons.
    note[STATE_FIELD] = json.dumps(json.loads(note[STATE_FIELD]), ensure_ascii=False)
    before = dict(note)
    plan = refresh.plan_example_refresh(collection, report(("時間",)), Settings())
    assert len(plan.updates) == 1 and not plan.updates[0].migration
    assert refresh.apply_example_refresh(collection, plan).updated == 1
    assert notes[1]["VocabExamples"] == before["VocabExamples"]
    assert not refresh.plan_example_refresh(collection, report(("時間",)), Settings()).updates


def test_damaged_baseline_does_not_block_dictionary_refresh(setup):
    collection, notes = setup
    note = add(notes)
    note[STATE_FIELD] = "damaged"
    settings = Settings(refresh=RefreshSettings(update_examples=False, update_dictionary_data=True))
    plan = refresh.plan_example_refresh(collection, report(), settings)
    assert not plan.conflicts
    assert refresh.apply_example_refresh(collection, plan).updated == 1
    assert not refresh.plan_example_refresh(collection, report(), settings).updates


def test_tracking_version_does_not_block_managed_field_replacement(setup):
    import json

    collection, notes = setup
    note = add(notes)
    saved = json.loads(note[STATE_FIELD])
    saved["version"] = 2
    note[STATE_FIELD] = json.dumps(saved)
    plan = refresh.plan_example_refresh(collection, report(), Settings())
    assert not plan.conflicts
    assert refresh.apply_example_refresh(collection, plan).updated == 1


@pytest.mark.parametrize("mode", ("recognition", "production"))
def test_known_editor_damage_auto_repairs_metadata_only_and_is_idempotent(setup, mode):
    import json

    from test_examples_state import editor_damaged_state

    collection, notes = setup
    note = add(notes, mode=mode)
    recorded = json.loads(note[STATE_FIELD])["fields"]
    note[STATE_FIELD] = editor_damaged_state(recorded)
    before = dict(note)
    plan = refresh.plan_example_refresh(collection, report(("時間",)), Settings())
    assert len(plan.updates) == 1 and not plan.updates[0].migration
    assert not plan.conflicts
    assert refresh.apply_example_refresh(collection, plan).updated == 1
    assert {k: v for k, v in notes[1].items() if k != STATE_FIELD} == {
        k: v for k, v in before.items() if k != STATE_FIELD
    }
    assert not refresh.plan_example_refresh(collection, report(("時間",)), Settings()).updates


def test_editor_damage_and_managed_edits_are_replaced(setup):
    import json

    from test_examples_state import editor_damaged_state

    collection, notes = setup
    note = add(notes)
    note[STATE_FIELD] = editor_damaged_state(json.loads(note[STATE_FIELD])["fields"])
    note["VocabExamples"] = "My own managed-field changes"
    plan = refresh.plan_example_refresh(collection, report(), Settings())
    assert not plan.conflicts
    assert refresh.apply_example_refresh(collection, plan).updated == 1
    assert "時計" in notes[1]["VocabExamples"]


def test_refresh_uses_anki_only_front_and_dictionary_back_without_leaking_clues(setup, monkeypatch):
    from katanki.generation.examples import lines, words_for_side

    collection, notes = setup
    note = add(notes, mode="production")
    note["UserExamples"] = "<div>時々</div>"
    monkeypatch.setattr(
        refresh,
        "selected_words",
        lambda choices: SimpleNamespace(
            lookup=lambda key: ("時代", "時計"),
            attribution="Synthetic dictionary",
        ),
    )
    options = CardSettings(
        example_source="discovered_and_default", front_example_source="discovered"
    )
    settings = Settings(cards=(options, options, CardSettings()))
    plan = refresh.plan_example_refresh(collection, report(("時間",)), settings)
    assert len(plan.updates) == 1 and not plan.updates[0].migration
    after = dict(plan.updates[0].after)
    assert lines(after["Prompt"]) == ("time", "__間")
    assert words_for_side(after["VocabExamples"], "front") == ("時間",)
    assert words_for_side(after["VocabExamples"], "back") == ("時間", "時代", "時計")
    assert refresh.apply_example_refresh(collection, plan).updated == 1
    assert notes[1]["UserExamples"] == "<div>時々</div>"
    assert not refresh.plan_example_refresh(collection, report(("時間",)), settings).updates


def test_dictionary_data_only_refresh_retains_saved_front_side_selection(setup):
    from katanki.generation.examples import encode_state, lines, managed_fields

    collection, notes = setup
    note = add(notes, mode="production")
    note["VocabExamples"] = (
        '<div data-front="true" data-back="true" data-source="vocabulary">時間</div>'
        '<div data-front="false" data-back="true" data-source="default">時計</div>'
    )
    note[STATE_FIELD] = encode_state(managed_fields(note, note.identity))
    settings = Settings(refresh=RefreshSettings(update_examples=False, update_dictionary_data=True))
    plan = refresh.plan_example_refresh(collection, report(("時間",)), settings)
    assert all("__計" not in dict(update.after).get("Prompt", "") for update in plan.updates)
    if plan.updates:
        assert lines(dict(plan.updates[0].after)["Prompt"]) == ("time", "__間")


def test_hiding_front_examples_keeps_dictionary_words_on_back(setup, monkeypatch):
    from katanki.generation.examples import words_for_side

    collection, notes = setup
    add(notes, mode="production")
    monkeypatch.setattr(
        refresh,
        "selected_words",
        lambda choices: SimpleNamespace(
            lookup=lambda key: ("時代",), attribution="Synthetic dictionary"
        ),
    )
    options = CardSettings(
        show_examples=False,
        example_source="discovered_and_default",
        front_example_source="discovered",
    )
    settings = Settings(cards=(options, options, CardSettings()))
    plan = refresh.plan_example_refresh(collection, report(("時間",)), settings)
    assert len(plan.updates) == 1 and not plan.conflicts
    fields = dict(plan.updates[0].after)
    assert fields["Prompt"] == "time"
    assert fields["ExampleLimit"] == "-1"
    assert words_for_side(fields["VocabExamples"], "back") == ("時間", "時代")
    assert refresh.apply_example_refresh(collection, plan).updated == 1
    assert not refresh.plan_example_refresh(collection, report(("時間",)), settings).updates
