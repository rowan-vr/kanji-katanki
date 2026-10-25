"""Exercise host boundaries without installing Anki or Qt in the dev environment."""

import importlib.util
import logging
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock

import pytest

import katanki


@pytest.fixture
def host(monkeypatch):
    from katanki.dictionaries import updates

    monkeypatch.setattr(updates, "USER_DATA", None)
    aqt = ModuleType("aqt")
    aqt.mw = Mock()
    aqt.gui_hooks = Mock()
    qt = ModuleType("aqt.qt")
    qt.QTimer = Mock()
    qt.QAction = Mock()
    qt.QMenu = Mock()
    utils = ModuleType("aqt.utils")
    discovery = ModuleType("katanki.ui.refresh")
    discovery.open_refresh = Mock()
    utils.open_refresh = discovery.open_refresh
    utils.showWarning = Mock()
    for module in (aqt, qt, utils, discovery):
        monkeypatch.setitem(sys.modules, module.__name__, module)
    path = Path(katanki.__file__).parent / "anki" / "integration.py"
    spec = importlib.util.spec_from_file_location("katanki.anki._test_integration", path)
    integration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(integration)
    return integration, aqt, qt, utils


def test_command_delegates_to_refresh(host):
    integration, aqt, _, utils = host
    integration.refresh_and_generate()
    utils.open_refresh.assert_called_once_with(aqt.mw)
    assert aqt.mw.col.mock_calls == []
    utils.showWarning.assert_not_called()


def test_command_without_profile_shows_warning(host):
    integration, aqt, _, utils = host
    aqt.mw.col = None
    integration.refresh_and_generate()
    utils.open_refresh.assert_not_called()
    utils.showWarning.assert_called_once()


def test_dialog_failure_is_logged_and_reported(host, caplog):
    integration, _, _, utils = host
    utils.open_refresh.side_effect = RuntimeError("dialog failed")
    with caplog.at_level(logging.ERROR):
        integration.refresh_and_generate()
    assert "dialog failed" in caplog.text
    utils.showWarning.assert_called_once()


def test_repeated_registration_does_not_add_a_second_menu(host):
    integration, aqt, qt, _ = host
    menu = qt.QMenu.return_value
    aqt.mw.menuBar().findChild.side_effect = [None, menu]
    integration.register()
    integration.register()
    qt.QMenu.assert_called_once()
    qt.QAction.assert_any_call("New Kanji Cards", menu)
    qt.QAction.assert_any_call("Refresh and generate Kanji Cards", menu)
    qt.QAction.assert_any_call("Statistics", menu)
    assert all(call.args[0] != "Analyze Collection" for call in qt.QAction.call_args_list)
    aqt.mw.menuBar().addMenu.assert_called_once_with(menu)
    qt.QAction.return_value.triggered.connect.assert_any_call(integration.refresh_and_generate)
    qt.QAction.return_value.triggered.connect.assert_any_call(integration.settings)
    aqt.mw.form.menuTools.addMenu.assert_not_called()
    aqt.gui_hooks.profile_did_open.append.assert_any_call(integration._check_dictionary_updates)


def test_bootstrap_failure_does_not_escape_even_if_warning_fails(host, monkeypatch, caplog):
    _, _, _, utils = host
    monkeypatch.setattr(katanki, "find_spec", lambda name: object())
    failing_integration = ModuleType("katanki.anki.integration")
    failing_integration.register = Mock(side_effect=RuntimeError("registration failed"))
    monkeypatch.setitem(sys.modules, "katanki.anki.integration", failing_integration)
    utils.showWarning.side_effect = RuntimeError("warning failed")
    with caplog.at_level(logging.ERROR):
        katanki.bootstrap()
    assert "registration failed" in caplog.text
    assert "warning failed" in caplog.text


def test_settings_command_opens_dialog_without_collection_writes(host, monkeypatch):
    integration, aqt, _, utils = host
    settings_ui = ModuleType("katanki.ui.settings")
    settings_ui.open_settings = Mock()
    monkeypatch.setitem(sys.modules, settings_ui.__name__, settings_ui)
    integration.settings()
    settings_ui.open_settings.assert_called_once_with(aqt.mw)
    assert aqt.mw.col.mock_calls == []
    utils.showWarning.assert_not_called()


def test_settings_command_requires_profile(host):
    integration, aqt, _, utils = host
    aqt.mw.col = None
    integration.settings()
    utils.showWarning.assert_called_once()


def test_manual_command_opens_entry_without_collection_writes(host, monkeypatch):
    integration, aqt, _, utils = host
    manual = ModuleType("katanki.ui.manual")
    manual.open_manual = Mock()
    monkeypatch.setitem(sys.modules, manual.__name__, manual)
    integration.new_kanji_cards()
    manual.open_manual.assert_called_once_with(aqt.mw)
    assert aqt.mw.col.mock_calls == []
    utils.showWarning.assert_not_called()


def test_manual_command_requires_profile(host):
    integration, aqt, _, utils = host
    aqt.mw.col = None
    integration.new_kanji_cards()
    utils.showWarning.assert_called_once()


def test_statistics_command_opens_window_without_collection_writes(host, monkeypatch):
    integration, aqt, _, utils = host
    dashboard = ModuleType("katanki.ui.dashboard")
    dashboard.open_statistics = Mock()
    monkeypatch.setitem(sys.modules, dashboard.__name__, dashboard)
    integration.statistics()
    dashboard.open_statistics.assert_called_once_with(aqt.mw)
    assert aqt.mw.col.mock_calls == []
    utils.showWarning.assert_not_called()


def test_statistics_command_requires_profile(host):
    integration, aqt, _, utils = host
    aqt.mw.col = None
    integration.statistics()
    utils.showWarning.assert_called_once()
