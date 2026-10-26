"""First-run scheduling and real-widget setup persistence."""

import importlib
import sys
from dataclasses import replace
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

from katanki.anki.onboarding import COMPLETED_KEY, FirstRunSetup
from katanki.config import Settings, from_dict


@pytest.mark.parametrize("completed", [False, True])
def test_setup_only_scheduled_until_completed(completed, monkeypatch):
    collection = Mock()
    collection.get_config.return_value = completed
    mw = SimpleNamespace(col=collection, state="deckBrowser", app=Mock(), progress=Mock())
    mw.app.activeModalWidget.return_value = None
    mw.progress.busy.return_value = False
    ui = ModuleType("katanki.ui.onboarding")
    ui.open_onboarding = Mock()
    monkeypatch.setitem(sys.modules, ui.__name__, ui)
    controller = FirstRunSetup(mw, Mock())
    controller.profile_opened()
    controller.run_pending()
    controller.run_pending()
    assert ui.open_onboarding.call_count == (0 if completed else 1)
    collection.set_config.assert_not_called()


@pytest.mark.parametrize("busy", ["modal", "progress", "review", "switch"])
def test_setup_waits_for_idle_and_does_not_follow_profile_switch(busy):
    collection = Mock()
    collection.get_config.return_value = False
    mw = SimpleNamespace(col=collection, state="deckBrowser", app=Mock(), progress=Mock())
    mw.app.activeModalWidget.return_value = None
    mw.progress.busy.return_value = False
    controller = FirstRunSetup(mw, Mock())
    controller.profile_opened()
    if busy == "modal":
        mw.app.activeModalWidget.return_value = object()
    elif busy == "progress":
        mw.progress.busy.return_value = True
    elif busy == "review":
        mw.state = "review"
    else:
        mw.col = object()
    controller.run_pending()
    assert controller.pending_collection is (None if busy == "switch" else collection)


@pytest.fixture
def wizard(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PyQt6 import QtCore, QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    qt = ModuleType("aqt.qt")
    for module in (QtWidgets, QtCore):
        qt.__dict__.update(
            {name: getattr(module, name) for name in dir(module) if name.startswith("Q")}
        )
    monkeypatch.setitem(sys.modules, "aqt", ModuleType("aqt"))
    monkeypatch.setitem(sys.modules, "aqt.qt", qt)
    utils = ModuleType("aqt.utils")
    utils.showWarning = Mock()
    utils.showInfo = Mock()
    monkeypatch.setitem(sys.modules, "aqt.utils", utils)
    for name in ("katanki.ui.sources", "katanki.ui.onboarding"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    module = importlib.import_module("katanki.ui.onboarding")
    monkeypatch.setattr(
        "katanki.ui.sources.scan_sources",
        lambda _: ([(1, "Vocabulary")], [(2, "Japanese", ("Expression",))]),
    )
    mw = QtWidgets.QWidget()
    mw.col = Mock()
    saved = replace(Settings(), statistics_selection=(("jlpt", "n5"),))
    mw.col.get_config.side_effect = lambda key, default=None: (
        saved.to_dict() if key == "katanki_settings" else default
    )
    mw.col.decks.all_names_and_ids.return_value = [SimpleNamespace(id=1, name="Kanji")]
    dialog = module.OnboardingDialog(mw)
    yield dialog, utils, saved
    dialog.close()
    mw.close()
    app.processEvents()
    for name in ("katanki.ui.sources", "katanki.ui.onboarding"):
        sys.modules.pop(name, None)


@pytest.mark.parametrize("dismiss", ["cancel", "close"])
def test_dismiss_marks_seen_without_saving_choices_and_explains_restart(wizard, dismiss):
    dialog, utils, _ = wizard
    if dismiss == "close":
        dialog.show()
        dialog.close()
    else:
        dialog.reject()
    dialog.collection.set_config.assert_called_once_with(COMPLETED_KEY, True)
    utils.showInfo.assert_called_once()
    assert "Katanki → Settings → Refresh" in utils.showInfo.call_args.args[0]
    assert "will not open automatically again" in utils.showInfo.call_args.args[0]
    dialog.reject()
    assert utils.showInfo.call_count == 1


def test_finish_saves_manual_setup_and_preserves_advanced_choices(wizard):
    dialog, utils, saved = wizard
    dialog.manual_only.setChecked(True)
    for checkbox in dialog.categories.values():
        checkbox.setChecked(False)
    dialog.appearance["recognition"][0].setCurrentIndex(2)
    dialog.accept()
    utils.showWarning.assert_not_called()
    writes = dict(call.args for call in dialog.collection.set_config.call_args_list)
    assert writes[COMPLETED_KEY] is True
    result = from_dict(writes["katanki_settings"])
    assert not result.refresh.enabled
    assert not result.sources
    assert not result.card_settings("recognition").show_examples
    assert result.statistics_selection == saved.statistics_selection
    assert result.dictionaries == saved.dictionaries


def test_automatic_generation_requires_sources_and_destination(wizard):
    dialog, _, _ = wizard
    dialog.automatic.setChecked(True)
    with pytest.raises(ValueError, match="destination"):
        dialog._generation()
    for category in ("recognition", "production"):
        dialog.decks[category].setCurrentIndex(1)
    dialog.manual_only.setChecked(True)
    assert not dialog.automatic.isChecked()
    assert not dialog.start_now.isChecked()
    dialog.automatic.setChecked(True)
    dialog.categories["recognition"].setChecked(True)
    with pytest.raises(ValueError, match="vocabulary sources"):
        dialog._generation()
    dialog.manual_only.setChecked(False)
    assert dialog._generation()[0].auto_generate


def test_finish_enables_automatic_triggers_and_keeps_card_defaults(wizard, monkeypatch):
    from katanki.config import SourceRule

    dialog, utils, saved = wizard
    rules = (SourceRule("*", 2, ("Expression",)),)
    monkeypatch.setattr(dialog, "_rules", lambda: rules)
    dialog.automatic.setChecked(True)
    for category in ("recognition", "production"):
        dialog.decks[category].setCurrentIndex(1)
    dialog.accept()
    utils.showWarning.assert_not_called()
    writes = dict(call.args for call in dialog.collection.set_config.call_args_list)
    result = from_dict(writes["katanki_settings"])
    assert writes[COMPLETED_KEY] is True
    assert result.refresh.enabled
    assert result.refresh.on_profile_open and result.refresh.after_sync
    assert result.sources == rules
    for category in ("recognition", "production", "parts"):
        assert result.card_settings(category) == saved.card_settings(category)
    assert result.generation_settings("recognition").target_deck_id == 1


@pytest.mark.parametrize("migrate", [False, True])
def test_finishing_routes_to_migration_or_discovery_once(wizard, monkeypatch, migrate):
    dialog, _, _ = wizard
    module = sys.modules["katanki.ui.onboarding"]
    migration = ModuleType("katanki.ui.migration")
    migration.open_migration = Mock()
    refresh = ModuleType("katanki.ui.refresh")
    refresh.open_refresh = Mock()
    monkeypatch.setitem(sys.modules, migration.__name__, migration)
    monkeypatch.setitem(sys.modules, refresh.__name__, refresh)
    monkeypatch.setattr(module, "OnboardingDialog", lambda _: dialog)
    monkeypatch.setattr(dialog, "exec", lambda: module.QWizard.DialogCode.Accepted)
    scheduled = []
    monkeypatch.setattr(module.QTimer, "singleShot", lambda _, callback: scheduled.append(callback))
    dialog.migrate_existing.setChecked(migrate)
    assert dialog.start_now.isEnabled() is not migrate
    module.open_onboarding(dialog.mw)
    assert len(scheduled) == 1
    scheduled[0]()
    assert migration.open_migration.call_count == int(migrate)
    assert refresh.open_refresh.call_count == int(not migrate)


def test_first_setup_card_defaults_and_independent_front_back_choices(wizard):
    original, utils, _ = wizard
    module = sys.modules["katanki.ui.onboarding"]
    original.collection.get_config.side_effect = lambda key, default=None: default
    dialog = module.OnboardingDialog(original.mw)
    try:
        for category in ("recognition", "production"):
            front, back, front_furigana, back_furigana = dialog.appearance[category]
            assert front.currentData() == "discovered"
            assert back.currentData() == "discovered_and_default"
            assert front_furigana.isChecked() and back_furigana.isChecked()
        front, back, front_furigana, back_furigana = dialog.appearance["production"]
        front.setCurrentIndex(1)
        back.setCurrentIndex(0)
        front_furigana.setChecked(False)
        dialog.manual_only.setChecked(True)
        dialog.accept()
        utils.showWarning.assert_not_called()
        writes = dict(call.args for call in dialog.collection.set_config.call_args_list)
        result = from_dict(writes["katanki_settings"])
        recognition = result.card_settings("recognition")
        assert recognition.front_source == "discovered"
        assert recognition.example_source == "discovered_and_default"
        assert recognition.front_furigana and recognition.furigana
        production = result.card_settings("production")
        assert production.front_source == "discovered_and_default"
        assert production.example_source == "discovered"
        assert not production.front_furigana and production.furigana
    finally:
        dialog.close()
