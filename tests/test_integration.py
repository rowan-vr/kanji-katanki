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
    aqt = ModuleType("aqt")
    aqt.mw = Mock()
    qt = ModuleType("aqt.qt")
    qt.QAction = Mock()
    qt.QMenu = Mock()
    utils = ModuleType("aqt.utils")
    discovery = ModuleType("katanki.ui.discovery")
    discovery.open_discovery = Mock()
    utils.open_discovery = discovery.open_discovery
    utils.showWarning = Mock()
    for module in (aqt, qt, utils, discovery):
        monkeypatch.setitem(sys.modules, module.__name__, module)
    path = Path(katanki.__file__).parent / "anki" / "integration.py"
    spec = importlib.util.spec_from_file_location("katanki.anki._test_integration", path)
    integration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(integration)
    return integration, aqt, qt, utils


def test_command_delegates_to_discovery_dialog(host):
    integration, aqt, _, utils = host
    integration.analyze_collection()
    utils.open_discovery.assert_called_once_with(aqt.mw)
    assert aqt.mw.col.mock_calls == []
    utils.showWarning.assert_not_called()


def test_command_without_profile_shows_warning(host):
    integration, aqt, _, utils = host
    aqt.mw.col = None
    integration.analyze_collection()
    utils.open_discovery.assert_not_called()
    utils.showWarning.assert_called_once()


def test_dialog_failure_is_logged_and_reported(host, caplog):
    integration, _, _, utils = host
    utils.open_discovery.side_effect = RuntimeError("dialog failed")
    with caplog.at_level(logging.ERROR):
        integration.analyze_collection()
    assert "dialog failed" in caplog.text
    utils.showWarning.assert_called_once()


def test_repeated_registration_does_not_add_a_second_menu(host):
    integration, aqt, qt, _ = host
    menu = qt.QMenu.return_value
    aqt.mw.form.menuTools.findChild.side_effect = [None, menu]
    integration.register()
    integration.register()
    qt.QMenu.assert_called_once()
    aqt.mw.form.menuTools.addMenu.assert_called_once_with(menu)
    qt.QAction.return_value.triggered.connect.assert_called_once_with(
        integration.analyze_collection
    )


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
