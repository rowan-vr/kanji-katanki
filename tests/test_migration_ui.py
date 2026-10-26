"""Regression coverage for source setup without hidden category opt-in."""

import importlib
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest
from test_statistics_ui import qt_host as qt_host


@pytest.fixture
def migration_ui(qt_host, monkeypatch):
    operations = sys.modules["aqt.operations"]
    monkeypatch.setattr(
        operations.QueryOp, "with_backend_progress", lambda self, _: self, raising=False
    )
    monkeypatch.setattr(operations, "CollectionOp", Mock(), raising=False)
    utils = ModuleType("aqt.utils")
    utils.showInfo, utils.showWarning = Mock(), Mock()
    monkeypatch.setitem(sys.modules, "aqt.utils", utils)
    monkeypatch.delitem(sys.modules, "katanki.ui.migration", raising=False)
    module = importlib.import_module("katanki.ui.migration")
    model = {
        "id": 10,
        "name": "Source",
        "type": 0,
        "flds": [{"name": "Front"}, {"name": "Back"}],
        "tmpls": [{"ord": 0, "name": "Card 1"}, {"ord": 1, "name": "Card 2"}],
    }
    qt_host.window.col = SimpleNamespace(
        models=SimpleNamespace(all=lambda: [model]),
        decks=SimpleNamespace(all_names_and_ids=lambda: [SimpleNamespace(id=1, name="Old cards")]),
    )
    yield SimpleNamespace(host=qt_host, module=module, model=model, utils=utils)
    sys.modules.pop("katanki.ui.migration", None)


def test_source_setup_guides_incomplete_choices_without_error(migration_ui):
    ui = migration_ui
    dialog = ui.module.MigrationDialog(ui.host.window)
    assert set(dialog.mappings) == {"recognition", "production"}
    assert not dialog.findChildren(ui.host.qt.QCheckBox)
    assert not dialog.preview_button.isEnabled()
    dialog.preview()
    ui.utils.showWarning.assert_not_called()
    assert not ui.host.operations
    source = dialog.mappings["recognition"]
    assert not source.model.isEnabled()
    source.deck.setCurrentIndex(1)
    assert source.active() and source.model.isEnabled()
    assert "note type" in source.status.text()
    assert not hasattr(source, "template")
    source.model.setCurrentIndex(1)
    assert not dialog.preview_button.isEnabled()
    assert "character field" in source.status.text()
    source.field.setCurrentIndex(1)
    assert dialog.preview_button.isEnabled()
    assert not dialog.mappings["production"].active()
    dialog.preview()
    assert len(ui.host.operations) == 1
    assert dialog.busy and not dialog.apply_button.isEnabled()
    ui.utils.showWarning.assert_not_called()
    dialog._busy(False)
    dialog.reject()


def test_unambiguous_character_field_is_selected_without_card_type(migration_ui):
    ui = migration_ui
    ui.model["flds"] = [{"name": "Character"}, {"name": "Meaning"}]
    ui.model["tmpls"] = [
        {"ord": 0, "name": "Recognition"},
        {"ord": 1, "name": "Production"},
    ]
    dialog = ui.module.MigrationDialog(ui.host.window)
    for mode in ("recognition", "production"):
        source = dialog.mappings[mode]
        source.deck.setCurrentIndex(1)
        source.model.setCurrentIndex(1)
        assert source.complete()
        assert not hasattr(source.source(), "template")
        assert source.source().field == "Character"
    assert dialog.preview_button.isEnabled()
    # Choosing Skip invalidates previous approval, while the other direction stays usable.
    dialog.plan = SimpleNamespace(items=(object(),))
    dialog.apply_button.setEnabled(True)
    dialog.mappings["production"].deck.setCurrentIndex(0)
    assert dialog.plan is None and not dialog.apply_button.isEnabled()
    assert dialog.preview_button.isEnabled()
    dialog.reject()


def test_progress_updates_only_popup_on_main_thread(migration_ui):
    ui = migration_ui
    queued = []
    ui.host.window.taskman = SimpleNamespace(run_on_main=queued.append)
    ui.host.window.progress = Mock()
    dialog = ui.module.MigrationDialog(ui.host.window)
    dialog._busy(True)
    dialog._progress("Converting 景", 3, 10)
    assert dialog.summary.text() == "Preparing migration…"
    ui.host.window.progress.update.assert_not_called()
    queued.pop()()
    assert dialog.summary.text() == "Preparing migration…"
    assert not dialog.findChildren(ui.host.qt.QProgressBar)
    popup_update = SimpleNamespace()
    dialog._popup_progress(None, popup_update)
    assert (popup_update.label, popup_update.value, popup_update.max) == (
        "Converting 景 (3 of 10)",
        3,
        10,
    )
    ui.host.window.progress.update.assert_called_once_with(
        label="Converting 景 (3 of 10)", value=3, max=10
    )
    dialog._progress("Finishing conversion…")
    dialog._busy(False)
    finished_text = dialog.summary.text()
    queued.pop()()
    assert dialog.summary.text() == finished_text
    ui.host.window.progress.update.assert_called_once()
    dialog.reject()


def test_progress_throttles_intermediate_updates_but_keeps_completion(migration_ui, monkeypatch):
    ui = migration_ui
    queued = []
    ui.host.window.taskman = SimpleNamespace(run_on_main=queued.append)
    ui.host.window.progress = Mock()
    stamps = iter((1.0, 1.01, 1.02))
    monkeypatch.setattr(ui.module, "monotonic", lambda: next(stamps))
    dialog = ui.module.MigrationDialog(ui.host.window)
    dialog._busy(True)
    dialog._progress("Converting cards", 1, 10)
    dialog._progress("Converting cards", 2, 10)
    dialog._progress("Converting cards", 10, 10)
    assert len(queued) == 2
    for callback in queued:
        callback()
    assert dialog._progress_state == ("Converting cards (10 of 10)", 10, 10)
    dialog._busy(False)
    dialog.reject()
