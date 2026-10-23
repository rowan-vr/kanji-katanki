"""Manual candidates share discovery's classification and configured planning."""

from pathlib import Path
from unittest.mock import Mock

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
    result = refresh.prepare_manual(collection, settings, "景景、abc かな 123\n景")
    assert result.report.scan.candidates == ("景",)
    assert result.report.scan.vocabulary == ()
    assert result.report.entries[0].character == "景"
    assert result.preview is preview.return_value
    assert preview.call_args.kwargs["generation_settings"] is settings
    assert preview.call_args.kwargs["recognition"] == ("景",)
    assert preview.call_args.kwargs["production"] == ("景",)
    collection.find_notes.assert_not_called()


def test_manual_planning_respects_ignores_and_disabled_categories(monkeypatch):
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
    assert choices["recognition"] == choices["production"] == ()
    assert not choices["include_primitives"]
    assert choices["ignored"] == ignored
