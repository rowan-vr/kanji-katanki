"""Front clue sources and back reference sources are independent and portable."""

from dataclasses import replace

import pytest

from katanki.common.models import DiscoveryReport, KanjiEntry, ScanResult
from katanki.config import CardSettings, Settings, from_dict
from katanki.dictionaries.words import WordSuggestions
from katanki.generation.examples import words_for_side
from katanki.generation.preview import build_preview


def report():
    return DiscoveryReport(
        ScanResult(1, ("時",), ("時間割",)),
        (KanjiEntry("時", (), (), ("time",)),),
        (),
        (),
        True,
        (),
    )


def preview(front, back):
    options = CardSettings(example_source=back, front_example_source=front, example_limit=0)
    return build_preview(
        report(),
        (),
        recognition=("時",),
        production=("時",),
        include_primitives=False,
        card_settings={"recognition": options, "production": options},
        word_suggestions=WordSuggestions([("時間", "じかん", 200), ("時計", "とけい", 100)]),
    )


@pytest.mark.parametrize("front", ("discovered", "discovered_and_default"))
@pytest.mark.parametrize("back", ("discovered", "discovered_and_default"))
def test_each_side_uses_its_own_source_pool_without_changing_note_fields(front, back):
    result = preview(front, back)
    own = ("時間割",)
    combined = ("時間割", "時間", "時計")
    for content in result.contents:
        fields = content.fields()
        assert words_for_side(fields["VocabExamples"], "front") == (
            own if front == "discovered" else combined
        )
        assert words_for_side(fields["VocabExamples"], "back") == (
            own if back == "discovered" else combined
        )
        assert "UserExamples" not in fields  # Editable examples are deferred to Phase 6.
        if content.identity.note_type == "kanji-production":
            assert content.prompt == (
                "time\n\n__間割" if front == "discovered" else "time\n\n__間割\n__間\n__計"
            )


def test_back_only_dictionary_words_cannot_disambiguate_a_production_front():
    discovery = DiscoveryReport(
        ScanResult(2, ("時", "刻"), ("時", "刻")),
        (KanjiEntry("時", (), (), ("time",)), KanjiEntry("刻", (), (), ("time",))),
        (),
        (),
        True,
        (),
    )
    choices = dict(
        recognition=(),
        production=("時", "刻"),
        include_primitives=False,
        word_suggestions=WordSuggestions([("時計", "とけい", 200), ("刻印", "こくいん", 200)]),
    )
    options = CardSettings(
        example_source="discovered_and_default", front_example_source="discovered"
    )
    result = build_preview(discovery, (), card_settings={"production": options}, **choices)
    assert all(item.outcome == "unavailable" for item in result.plan.items)
    result = build_preview(
        discovery,
        (),
        card_settings={
            "production": replace(options, front_example_source="discovered_and_default")
        },
        **choices,
    )
    assert all(item.outcome == "create" for item in result.plan.items)


@pytest.mark.parametrize("source", ("discovered", "discovered_and_default"))
def test_version_six_shared_source_is_preserved_on_both_sides(source):
    saved = Settings(cards=tuple(CardSettings(example_source=source) for _ in range(3))).to_dict()
    saved["version"] = 6
    for entry in saved["cards"].values():
        entry.pop("front_example_source")
    restored = from_dict(saved)
    assert restored.to_dict()["version"] == 7
    for options in restored.cards:
        assert options.example_source == source
        assert options.front_source == source
        assert options.front_example_source is None


def test_independent_sources_survive_settings_roundtrip():
    options = CardSettings(
        example_source="discovered_and_default", front_example_source="discovered"
    )
    settings = Settings(cards=(options, options, CardSettings()))
    assert from_dict(settings.to_dict()) == settings


@pytest.mark.parametrize("bad", ([], 1, False, "dictionary", ""))
def test_invalid_front_sources_fail_without_silently_changing_the_back(bad):
    saved = Settings().to_dict()
    saved["cards"]["production"]["front_example_source"] = bad
    with pytest.raises(ValueError):
        from_dict(saved)


def test_legacy_unmarked_examples_remain_available_on_both_sides():
    legacy = '<div data-source="vocabulary">時間</div><div data-source="default">時計</div>'
    assert words_for_side(legacy, "front") == ("時間", "時計")
    assert words_for_side(legacy, "back") == ("時間", "時計")


def test_dictionary_credits_are_deduplicated_before_first_refresh():
    from katanki.generation.cards import CardContent
    from katanki.generation.planner import Identity

    content = CardContent(
        Identity("kanji-recognition", "丈"),
        "丈",
        attribution=("Dictionary & contributors", "Stroke source", "Dictionary & contributors"),
    )
    assert content.fields()["Attribution"] == "Dictionary &amp; contributors<br>Stroke source"
