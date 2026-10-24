"""Exercise saved preferences with real Qt widgets, without launching Anki."""

import importlib.util
import sys
from dataclasses import replace
from pathlib import Path
from types import ModuleType

import pytest

from katanki.config import CardSettings


@pytest.fixture
def panel_factory(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PyQt6 import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    # Anki re-exports these widgets through aqt.qt. Use the same real widgets
    # while keeping the test independent of the full Anki application.
    monkeypatch.setitem(sys.modules, "aqt", ModuleType("aqt"))
    monkeypatch.setitem(sys.modules, "aqt.qt", QtWidgets)
    path = Path(__file__).parents[1] / "src/katanki/ui/card_settings.py"
    spec = importlib.util.spec_from_file_location("card_settings_ui_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    panels = []

    def create(category, settings):
        panel = module.CardSettingsPanel(category, settings)
        panels.append(panel)
        return panel

    yield create
    for panel in panels:
        panel.close()
        panel.deleteLater()
    app.processEvents()


@pytest.mark.parametrize("category", ("recognition", "production", "parts"))
@pytest.mark.parametrize(
    "saved",
    (
        CardSettings(),
        CardSettings(
            show_examples=False,
            example_source="discovered_and_default",
            front_example_source="discovered",
            example_limit=0,
            show_name=False,
            auto_refresh=False,
            furigana=True,
            include_new=False,
        ),
    ),
)
def test_opening_and_saving_preserves_all_preferences(panel_factory, category, saved):
    panel = panel_factory(category, saved)
    assert panel.settings() == saved
    if category == "parts":
        assert panel.limit.isHidden()
        assert not hasattr(panel, "front_source")
    else:
        assert panel.furigana.isEnabled()
        assert panel.front_furigana.isEnabled()
        assert not panel.word_status.isEnabled()


@pytest.mark.parametrize("category", ("recognition", "production"))
def test_front_and_back_choices_save_and_reopen_independently(panel_factory, category):
    original = CardSettings()
    panel = panel_factory(category, original)
    panel.front_source.setCurrentIndex(panel.front_source.findData("discovered"))
    panel.back_source.setCurrentIndex(panel.back_source.findData("discovered_and_default"))
    panel.examples.setChecked(False)
    panel.limit.setValue(2)
    panel.refresh.setChecked(False)
    expected = replace(
        original,
        front_example_source="discovered",
        example_source="discovered_and_default",
        show_examples=False,
        example_limit=2,
        auto_refresh=False,
    )
    assert panel.settings() == expected
    assert panel_factory(category, panel.settings()).settings() == expected
    assert original == CardSettings()


def test_explicit_matching_sources_remain_explicit(panel_factory):
    saved = CardSettings(front_example_source="discovered")
    assert panel_factory("recognition", saved).settings() == saved


def test_parts_choices_preserve_legacy_limit_and_word_options(panel_factory):
    saved = CardSettings(example_limit=3, furigana=True, include_new=False)
    panel = panel_factory("parts", saved)
    panel.name.setChecked(False)
    panel.examples.setChecked(False)
    panel.source.setCurrentIndex(panel.source.findData("discovered_and_default"))
    panel.refresh.setChecked(False)
    expected = replace(
        saved,
        show_name=False,
        show_examples=False,
        example_source="discovered_and_default",
        auto_refresh=False,
    )
    assert panel.settings() == expected
    assert panel_factory("parts", panel.settings()).settings() == expected


def test_furigana_switches_save_independently(panel_factory):
    panel = panel_factory("production", CardSettings(front_furigana=True))
    panel.front_furigana.setChecked(False)
    panel.furigana.setChecked(True)
    saved = panel.settings()
    assert not saved.front_furigana and saved.furigana
    panel = panel_factory("production", saved)
    panel.front_furigana.setChecked(True)
    panel.furigana.setChecked(False)
    assert panel.settings().front_furigana and not panel.settings().furigana
