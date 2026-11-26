"""Exercise the Generation tab with real Qt widgets, without launching Anki."""

import importlib
import sys
from types import ModuleType, SimpleNamespace

import pytest

from katanki.config import GenerationSettings, Settings


@pytest.fixture
def tab_factory(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PyQt6 import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    monkeypatch.setitem(sys.modules, "aqt", ModuleType("aqt"))
    monkeypatch.setitem(sys.modules, "aqt.qt", QtWidgets)
    monkeypatch.delitem(sys.modules, "katanki.ui.generation_settings", raising=False)
    module = importlib.import_module("katanki.ui.generation_settings")
    deck = SimpleNamespace(id=42, name="Kanji")
    mw = SimpleNamespace(
        col=SimpleNamespace(decks=SimpleNamespace(all_names_and_ids=lambda: [deck]))
    )
    tabs = []

    def create(settings):
        tab = module.GenerationTab(mw, settings)
        tabs.append(tab)
        return tab

    yield create
    for tab in tabs:
        tab.deleteLater()
    app.processEvents()
    sys.modules.pop("katanki.ui.generation_settings", None)


@pytest.mark.parametrize("ignore", (False, True))
def test_generation_tab_restores_shared_switch_and_category_panels(tab_factory, ignore):
    generation = (GenerationSettings(True, 42), GenerationSettings(), GenerationSettings())
    tab = tab_factory(Settings(generation=generation, ignore_suspended=ignore))
    assert tab.ignore_suspended.isChecked() is ignore
    assert [tab.tabs.tabText(i) for i in range(tab.tabs.count())] == [
        "Recognition",
        "Production",
        "Parts",
    ]
    assert tuple(panel.settings() for panel in tab.panels.values()) == generation
