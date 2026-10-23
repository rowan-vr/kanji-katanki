"""Automatic triggers only enter the approved workflow on an idle deck list."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from katanki.anki.automatic_refresh import AutomaticRefresh
from katanki.config import RefreshSettings, Settings, SourceRule, from_dict


@pytest.fixture
def automatic(monkeypatch):
    settings = Settings(sources=(SourceRule("*", 1, ("Front",)),), refresh=RefreshSettings(True))
    load = Mock(return_value=settings)
    monkeypatch.setattr("katanki.anki.automatic_refresh.load_settings", load)
    mw = SimpleNamespace(col=object(), state="deckBrowser", app=Mock(), progress=Mock())
    mw.app.activeModalWidget.return_value = None
    mw.progress.busy.return_value = False
    timer = Mock()
    return AutomaticRefresh(mw, timer), load


def test_triggers_coalesce_and_use_shared_review_workflow(automatic, monkeypatch):
    import sys
    from types import ModuleType

    ui = ModuleType("katanki.ui.refresh")
    ui.open_refresh = Mock()
    monkeypatch.setitem(sys.modules, ui.__name__, ui)
    controller, _ = automatic
    controller.profile_opened()
    controller.sync_finished()
    controller.run_pending()
    controller.run_pending()
    ui.open_refresh.assert_called_once_with(controller.mw, automatic=True)
    assert controller.pending_collection is None
    controller.timer.stop.assert_called()


@pytest.mark.parametrize("trigger", ["on_profile_open", "after_sync"])
def test_disabled_triggers_never_schedule(automatic, trigger):
    controller, load = automatic
    for refresh in (RefreshSettings(), replace(RefreshSettings(True), **{trigger: False})):
        load.return_value = replace(load.return_value, refresh=refresh)
        controller.request(trigger)
        assert controller.pending_collection is None
    controller.timer.start.assert_not_called()


@pytest.mark.parametrize("busy", ["review", "modal", "progress", "refresh"])
def test_busy_host_keeps_one_pending_run(automatic, busy):
    controller, _ = automatic
    controller.sync_finished()
    if busy == "review":
        controller.mw.state = "review"
    elif busy == "modal":
        controller.mw.app.activeModalWidget.return_value = object()
    elif busy == "progress":
        controller.mw.progress.busy.return_value = True
    else:
        controller.mw._katanki_refresh_running = True
    controller.run_pending()
    assert controller.pending_collection is controller.mw.col
    controller.timer.stop.assert_not_called()


@pytest.mark.parametrize("change", ["close", "switch", "disabled", "sources"])
def test_pending_run_cannot_outlive_profile_or_configuration(automatic, change):
    controller, load = automatic
    controller.profile_opened()
    if change == "close":
        controller.close()
    elif change == "switch":
        controller.mw.col = object()
    elif change == "disabled":
        load.return_value = replace(load.return_value, refresh=RefreshSettings())
    else:
        load.return_value = replace(load.return_value, sources=())
    controller.run_pending()
    assert controller.pending_collection is None
    controller.timer.stop.assert_called()


def test_invalid_configuration_is_logged_without_starting(automatic, caplog):
    controller, load = automatic
    load.side_effect = ValueError("Invalid saved sources")
    controller.profile_opened()
    controller.timer.start.assert_not_called()
    assert "Invalid saved sources" in caplog.text


def test_refresh_preferences_roundtrip_and_legacy_migration():
    settings = Settings(refresh=RefreshSettings(True, False, True, True, False, True))
    assert from_dict(settings.to_dict()) == settings
    for version in range(1, 6):
        saved = {"version": version}
        assert from_dict(saved).refresh == RefreshSettings()
        assert saved == {"version": version}


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        True,
        {"enabled": 1},
        {"after_sync": "false"},
        {"update_source_tags": 1},
        {"update_examples": "false"},
        {"update_dictionary_data": 1},
    ],
)
def test_invalid_refresh_preferences_fail_closed(value):
    with pytest.raises(ValueError):
        from_dict({"version": 6, "refresh": value})


def test_existing_version_six_settings_receive_card_update_defaults():
    saved = {"version": 6, "refresh": {"enabled": True, "after_sync": False}}
    refresh = from_dict(saved).refresh
    assert refresh.enabled
    assert not refresh.after_sync
    assert not refresh.update_source_tags
    assert refresh.update_examples
    assert not refresh.update_dictionary_data
    assert saved == {"version": 6, "refresh": {"enabled": True, "after_sync": False}}
