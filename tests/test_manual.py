"""Manual candidates share discovery's classification and configured planning."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from katanki.anki import refresh
from katanki.config import Settings
from katanki.generation.planner import Identity

FIXTURES = Path(__file__).parent / "fixtures"


def test_manual_input_classifies_unique_kanji_without_discovery_sources(monkeypatch):
    collection = Mock()
    monkeypatch.setattr(
        refresh,
        "dictionary_sources",
        lambda _: {"kanjidic2": FIXTURES / "kanjidic2.xml", "kanjivg": FIXTURES / "kanjivg"},
    )
    monkeypatch.setattr("katanki.anki.analysis.owned_identities", lambda *a, **k: {})
    monkeypatch.setattr(refresh, "load_ignored", lambda _: frozenset())
    preview = Mock()
    monkeypatch.setattr(refresh, "preview_generation", preview)
    settings = Settings()
    progress = Mock()
    result = refresh.prepare_manual(
        collection, settings, "景景、abc かな 123\n景", progress=progress
    )
    assert "Loading dictionaries" in progress.call_args_list[0].args[0]
    assert preview.call_args.kwargs["progress"] is progress
    assert result.report.scan.candidates == ("景",)
    assert result.report.scan.vocabulary == ()
    assert result.report.entries[0].character == "景"
    assert result.preview is preview.return_value
    assert preview.call_args.kwargs["generation_settings"].generation == settings.generation
    assert preview.call_args.kwargs["recognition"] == ("景",)
    assert preview.call_args.kwargs["production"] == ("景",)
    collection.find_notes.assert_not_called()


def test_manual_planning_respects_ignores_but_overrides_disabled_categories(monkeypatch):
    from dataclasses import replace

    from test_generation import report

    ignored = frozenset({Identity("kanji-recognition", "景")})
    monkeypatch.setattr(refresh, "analyze_scan", lambda *args: report())
    monkeypatch.setattr(refresh, "load_ignored", lambda _: ignored)
    preview = Mock()
    monkeypatch.setattr(refresh, "preview_generation", preview)
    settings = Settings()
    settings = replace(
        settings,
        generation=tuple(replace(item, auto_generate=False) for item in settings.generation),
    )
    refresh.prepare_manual(Mock(), settings, "景")
    choices = preview.call_args.kwargs
    assert choices["recognition"] == ("色",)
    assert choices["production"]
    assert choices["include_primitives"]
    assert choices["ignored"] == ignored


@pytest.mark.parametrize(
    "categories",
    [
        ("recognition",),
        ("production",),
        ("parts",),
        ("recognition", "production"),
        ("recognition", "production", "parts"),
    ],
)
def test_explicit_manual_category_overrides_automatic_settings(monkeypatch, categories):
    from dataclasses import replace

    from test_generation import report

    monkeypatch.setattr(refresh, "analyze_scan", lambda *args: report())
    monkeypatch.setattr(refresh, "load_ignored", lambda _: frozenset())
    preview = Mock()
    monkeypatch.setattr(refresh, "preview_generation", preview)
    settings = Settings()
    settings = replace(
        settings,
        generation=tuple(replace(item, auto_generate=False) for item in settings.generation),
    )
    refresh.prepare_manual(Mock(), settings, "景", categories=categories)
    choices = preview.call_args.kwargs
    assert bool(choices["recognition"]) is ("recognition" in categories)
    assert bool(choices["production"]) is ("production" in categories)
    assert choices["include_primitives"] is ("parts" in categories)
    assert choices["generation_settings"].generation == settings.generation
    assert all(not item.auto_generate for item in settings.generation)


@pytest.mark.parametrize("categories", [(), ("unknown",)])
def test_manual_rejects_empty_or_invalid_card_types(categories):
    with pytest.raises(ValueError, match="Choose"):
        refresh.prepare_manual(Mock(), Settings(), "景", categories=categories)


@pytest.mark.parametrize("show_examples,has_words", [(True, True), (True, False), (False, True)])
def test_manual_production_uses_jitendex_or_meaning_only(monkeypatch, show_examples, has_words):
    from dataclasses import replace

    from katanki.common.models import DiscoveryReport, KanjiEntry
    from katanki.dictionaries.words import WordSuggestions
    from katanki.generation.preview import build_preview

    def analyze(collection, scan, sources):
        return DiscoveryReport(
            scan,
            tuple(
                KanjiEntry(key, (), (), (meaning,))
                for key, meaning in (("日", "day"), ("本", "origin"), ("人", "person"))
            ),
            (),
            (),
            True,
            (),
        )

    def preview(collection, report, **choices):
        return build_preview(
            report,
            (),
            recognition=choices["recognition"],
            production=choices["production"],
            include_primitives=choices["include_primitives"],
            word_suggestions=WordSuggestions(
                (("日本語", "にほんご", 1), ("人間", "にんげん", 1)) if has_words else ()
            ),
            card_settings={
                "production": choices["generation_settings"].card_settings("production")
            },
        )

    monkeypatch.setattr(refresh, "analyze_scan", analyze)
    monkeypatch.setattr(refresh, "load_ignored", lambda _: frozenset())
    monkeypatch.setattr(refresh, "preview_generation", preview)
    settings = Settings()
    settings = replace(
        settings,
        generation=tuple(replace(item, auto_generate=False) for item in settings.generation),
        cards=tuple(replace(item, show_examples=show_examples) for item in settings.cards),
    )
    result = refresh.prepare_manual(Mock(), settings, "日本人", categories=("production",))
    assert result.report.scan.vocabulary == ()
    assert len(result.preview.plan.items) == 3
    assert all(item.outcome == "create" for item in result.preview.plan.items)
    prompts = {content.identity.key: content.prompt for content in result.preview.contents}
    if show_examples and has_words:
        assert "__本語" in prompts["日"]
        assert "日__語" in prompts["本"]
        assert "__間" in prompts["人"]
    else:
        assert prompts == {"日": "day", "本": "origin", "人": "person"}
    assert settings.card_settings("production").example_source == "discovered"
