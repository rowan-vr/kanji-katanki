"""Review selections preserve ownership, prerequisites, and card template semantics."""

from dataclasses import replace
from unittest.mock import Mock

import pytest

from katanki.anki.ignored import IGNORED_KEY, load_ignored, save_ignored
from katanki.common.models import DiscoveryReport, KanjiEntry, ScanResult
from katanki.config import GenerationSettings, Settings
from katanki.generation.cards import CardContent
from katanki.generation.destinations import CreationOptions
from katanki.generation.planner import GenerationPlan, Identity, LearningUnit, PlanItem
from katanki.generation.preview import GenerationPreview
from katanki.generation.review import exclude_ignored, render_card_preview


def test_ignored_choices_roundtrip_by_card_type_and_character_without_note_writes():
    collection = Mock()
    collection.get_config.return_value = []
    recognition = Identity("kanji-recognition", "景")
    production = Identity("kanji-production", "景")
    save_ignored(collection, {production, recognition})
    key, saved = collection.set_config.call_args.args
    assert key == IGNORED_KEY
    collection.get_config.return_value = saved
    assert load_ignored(collection) == {recognition, production}
    save_ignored(collection, load_ignored(collection) - {production})
    collection.get_config.return_value = collection.set_config.call_args.args[1]
    assert load_ignored(collection) == {recognition}
    assert not collection.add_note.called and not collection.remove_notes.called


@pytest.mark.parametrize(
    "data",
    [
        {},
        ["景"],
        [{"note_type": "unknown", "key": "景"}],
        [{"note_type": "kanji-production", "key": ""}],
    ],
)
def test_invalid_ignored_metadata_is_preserved(data):
    collection = Mock()
    collection.get_config.return_value = data
    with pytest.raises(ValueError):
        load_ignored(collection)
    collection.set_config.assert_not_called()


def test_ignoring_prerequisite_blocks_dependants_and_cannot_add_new_creations():
    part, kanji = Identity("primitive-recognition", "日"), Identity("kanji-recognition", "景")
    preview = GenerationPreview(
        GenerationPlan(
            (
                PlanItem(LearningUnit(part), "create", ""),
                PlanItem(LearningUnit(kanji, (part,)), "create", ""),
            )
        ),
        (),
        (),
        (CreationOptions(part, 10), CreationOptions(kanji, 20)),
    )
    excluded = exclude_ignored(preview, {part})
    assert all(item.outcome == "unavailable" for item in excluded.plan.items)
    assert excluded.creations == ()
    assert len(preview.creations) == 2
    existing = replace(
        preview,
        plan=GenerationPlan(
            (
                replace(preview.plan.items[0], outcome="skip"),
                preview.plan.items[1],
            )
        ),
    )
    result = exclude_ignored(existing, {part})
    assert [item.outcome for item in result.plan.items] == ["skip", "create"]
    assert [item.identity for item in result.creations] == [kanji]


def test_preview_escapes_source_content_and_renders_front_and_back_without_notes():
    identity = Identity("kanji-production", "景")
    content = CardContent(identity, "景", meanings=("<unsafe>",), prompt="scenery\n__色")
    front, back = render_card_preview(content)
    assert "scenery<br>__色" in front
    assert front in back
    assert "&lt;unsafe&gt;" in back and "<unsafe>" not in back
    assert "Stroke data unavailable" in back
    assert "{{" not in front and "{{" not in back


def test_disabled_category_and_ignored_character_never_enter_new_card_plan(monkeypatch):
    import katanki.anki.generation as generation
    import katanki.anki.refresh as refresh

    report = DiscoveryReport(
        ScanResult(1, ("景", "色"), ("景色",)),
        (KanjiEntry("景", (), (), ("scenery",)), KanjiEntry("色", (), (), ("color",))),
        (),
        (),
        True,
        (),
    )
    monkeypatch.setattr(refresh, "analyze", lambda *args: report)
    monkeypatch.setattr(refresh, "resolve_sources", lambda *args: ())
    monkeypatch.setattr(refresh, "dictionary_sources", lambda *args: {})
    owned = Mock(return_value={})
    monkeypatch.setattr(generation, "owned_identities", owned)
    collection = Mock()
    collection.get_config.return_value = [{"note_type": "kanji-recognition", "key": "景"}]
    settings = Settings(
        generation=(
            GenerationSettings(True, 10),
            GenerationSettings(False, 20),
            GenerationSettings(False),
        )
    )
    result = refresh.prepare_refresh(collection, settings)
    assert [item.identity for item in result.preview.creations] == [
        Identity("kanji-recognition", "色")
    ]
    assert [call.kwargs["note_type"] for call in owned.call_args_list] == ["kanji-recognition"]
    assert result.ignored_count == 1
