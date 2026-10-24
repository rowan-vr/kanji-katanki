"""Portable review content and conservative upgrades of the previous stock layouts."""

import json
from copy import deepcopy
from dataclasses import replace

import pytest

from katanki.common.models import NoteText, ScanResult
from katanki.generation import legacy_cards
from katanki.generation.cards import CSS, CardContent, note_type_spec
from katanki.generation.discovery import scan_notes
from katanki.generation.planner import NOTE_TYPES, Identity
from katanki.generation.preview import build_preview
from katanki.generation.template_updates import upgrade_stock_layout


@pytest.mark.parametrize("key", NOTE_TYPES)
def test_layout_has_a_separate_answer_and_no_instruction_prompt(key):
    spec = note_type_spec(key)
    assert "{{FrontSide}}" not in spec.back
    assert "question-card" not in spec.back
    assert "Write the" not in spec.front
    assert "Identify this" not in spec.front
    assert "answer-hero" in spec.back
    assert ("word-legend" in spec.back) == key.startswith("kanji")
    # Field schema stays stable; no media or JS is fetched during review.
    assert "Prompt" in spec.fields
    assert "<script src=" not in spec.back
    assert "pycmd(" not in spec.back


@pytest.mark.parametrize("key", NOTE_TYPES)
@pytest.mark.parametrize("css", legacy_cards.STYLES)
def test_exact_old_stock_layout_upgrades_without_touching_identity_or_fields(key, css):
    model = {
        "id": 123,
        "flds": [{"name": "Character"}],
        "css": css,
        "tmpls": [{"qfmt": legacy_cards.front(key), "afmt": legacy_cards.BACK}],
    }
    assert upgrade_stock_layout(model, key)
    spec = note_type_spec(key)
    assert model["tmpls"] == [{"qfmt": spec.front, "afmt": spec.back}]
    assert model["css"] == CSS
    assert model["id"] == 123 and model["flds"] == [{"name": "Character"}]
    assert not upgrade_stock_layout(model, key)


def test_custom_templates_and_styles_are_preserved():
    key = "kanji-recognition"
    for side in ("qfmt", "afmt"):
        model = {
            "css": legacy_cards.STYLES[0],
            "tmpls": [{"qfmt": legacy_cards.front(key), "afmt": legacy_cards.BACK}],
        }
        model["tmpls"][0][side] += "<div>My edits</div>"
        before = deepcopy(model)
        assert not upgrade_stock_layout(model, key)
        assert model == before
    model = {
        "css": ".card {color: purple}",
        "tmpls": [{"qfmt": legacy_cards.front(key), "afmt": legacy_cards.BACK}],
    }
    assert upgrade_stock_layout(model, key)
    assert model["css"] == ".card {color: purple}"


def test_word_status_snapshot_combines_duplicates_and_survives_source_removal():
    sources = [
        NoteText(("景色",), word_status="exists"),
        NoteText(("景色",), word_status="learned"),
        NoteText(("風景",), word_status="exists"),
        NoteText(("夜景",)),
    ]
    snapshot = scan_notes(sources)
    sources.clear()
    assert snapshot.vocabulary_statuses == (("景色", "learned"), ("風景", "exists"))
    content = CardContent(
        Identity("kanji-recognition", "景"),
        "景",
        examples=snapshot.vocabulary,
        example_statuses=snapshot.vocabulary_statuses,
    )
    fields = content.fields()
    assert 'data-status="learned">景色</div>' in fields["VocabExamples"]
    assert 'data-status="exists">風景</div>' in fields["VocabExamples"]
    assert 'data-status="missing">夜景</div>' in fields["VocabExamples"]
    assert (
        json.loads(fields["KatankiExamplesState"])["fields"]["VocabExamples"]
        == fields["VocabExamples"]
    )


def test_generation_copies_statuses_into_all_words_without_limiting_storage():
    from test_generation import report

    discovery = report()
    discovery = replace(
        discovery,
        scan=ScanResult(1, ("景",), ("景色",), vocabulary_statuses=(("景色", "learned"),)),
    )
    result = build_preview(
        discovery, (), recognition=("景",), production=("景",), include_primitives=False
    )
    for content in result.contents:
        assert 'data-status="learned">景色</div>' in content.fields()["VocabExamples"]


@pytest.mark.parametrize("limit", (0, 1, 5))
@pytest.mark.parametrize("visible", (False, True))
def test_generator_stores_full_configured_word_pool_independently_of_front_limits(limit, visible):
    from types import SimpleNamespace

    from test_generation import report

    from katanki.config import CardSettings
    from katanki.generation.examples import lines

    discovered = ("景色", "風景", "夜景")
    defaults = (
        "景色",
        "風景",
        "背景",
        "光景",
        "夜景",
        "情景",
        "景勝",
        "景品",
        "景気",
        "景観",
        "不景気",
        "好景気",
        "雪景色",
        "風景画",
        "夕景",
    )
    discovery = replace(report(), scan=ScanResult(3, ("景",), discovered))
    options = CardSettings(
        example_source="discovered_and_default", example_limit=limit, show_examples=visible
    )
    preview = build_preview(
        discovery,
        (),
        recognition=("景",),
        production=("景",),
        include_primitives=False,
        card_settings={"recognition": options, "production": options},
        word_suggestions=SimpleNamespace(lookup=lambda char: defaults),
    )
    for content in preview.contents:
        stored = lines(content.fields()["VocabExamples"])
        assert stored == tuple(dict.fromkeys((*sorted(discovered), *defaults)))
        assert len(stored) > 12
        if content.identity.note_type.endswith("production"):
            count = min(limit, len(stored)) if limit else len(stored)
            assert len(lines(content.fields()["Prompt"])) == 1 + (count if visible else 0)


@pytest.mark.parametrize("status", ("learned", "relearning", "learning", "new", "missing"))
def test_card_fields_retain_each_study_stage(status):
    content = CardContent(
        Identity("kanji-recognition", "時"),
        "時",
        examples=("時計",),
        example_statuses=(("時計", status),),
    )
    assert f'data-status="{status}">時計</div>' in content.fields()["VocabExamples"]


@pytest.mark.parametrize("key", NOTE_TYPES)
@pytest.mark.parametrize("early", (False, True))
def test_first_polished_stock_layout_upgrades_and_customized_copy_is_preserved(key, early):
    from katanki.generation import legacy_layout_v1 as previous

    kind, mode = key.split("-")
    label = ("Kanji" if kind == "kanji" else "Parts") + " · " + mode.title()
    front = (
        previous.PRODUCTION_FRONT
        if mode == "production"
        else (previous.PARTS_FRONT if kind == "primitive" else previous.RECOGNITION_FRONT)
    )
    back = (
        (previous.EARLY_BACK if early else previous.BACK)
        .replace("{{CardLabel}}", label)
        .replace("{{WordsLabel}}", "Words" if kind == "kanji" else "Related kanji")
        .replace("{{CardKind}}", kind)
        .replace(
            "{{WordLegend}}",
            previous.WORD_LEGEND.rstrip("\n")
            if early
            else previous.WORD_LEGEND
            if kind == "kanji"
            else "",
        )
    )
    model = {
        "css": previous.EARLY_CSS if early else previous.CSS,
        "tmpls": [{"qfmt": front.replace("{{CardLabel}}", label), "afmt": back}],
    }
    custom = deepcopy(model)
    custom["tmpls"][0]["afmt"] += "<p>My own layout</p>"
    before = deepcopy(custom)
    assert not upgrade_stock_layout(custom, key)
    assert custom == before
    assert upgrade_stock_layout(model, key)
    assert model["tmpls"][0]["afmt"] == note_type_spec(key).back
    assert model["css"] == CSS


def test_new_note_types_and_stock_templates_omit_deferred_user_examples():
    for key in NOTE_TYPES:
        spec = note_type_spec(key)
        assert "UserExamples" not in spec.fields
        assert "UserExamples" not in spec.front + spec.back
        assert "user-examples" not in spec.front + spec.back
