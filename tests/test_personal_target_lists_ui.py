"""Native personal-list interactions with real profile-local storage and modal review."""

import importlib
import sys
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_statistics_ui import qt_host  # noqa: F401

from katanki.anki.target_lists import PersonalTargetStore
from katanki.stats.targets import TargetGroup, TargetList, TargetRegistry, TargetSource


def target(characters="日月", *, list_id="personal"):
    return TargetList(
        list_id,
        "My <kanji> list",
        "1",
        "personal",
        TargetSource("Personal source", None, "1", "CC0", "Me", "user", "a" * 64),
        (TargetGroup("chosen", "Chosen", tuple(characters)),),
    )


@pytest.fixture
def panel_host(qt_host, tmp_path, monkeypatch):  # noqa: F811
    host = qt_host
    monkeypatch.delitem(sys.modules, "katanki.ui.target_lists", raising=False)
    module = importlib.import_module("katanki.ui.target_lists")
    store = PersonalTargetStore(tmp_path, "profile-a")
    collection = SimpleNamespace(path=str(tmp_path / "profile-a/collection.anki2"))
    host.window.col = collection
    owner = SimpleNamespace(mw=host.window, busy=False)
    monkeypatch.setattr("katanki.anki.target_lists.get_personal_target_store", lambda _: store)
    monkeypatch.setattr("katanki.config.load_settings", lambda _: SimpleNamespace(dictionaries=()))
    monkeypatch.setattr(
        "katanki.stats.sources.load_target_registry", lambda **_: TargetRegistry(())
    )
    monkeypatch.setattr(
        "katanki.dictionaries.registry.list_datasets",
        lambda: (
            SimpleNamespace(id="reserved", capabilities=("target_lists",)),
            SimpleNamespace(id="dictionary", capabilities=("kanji",)),
        ),
    )
    host.window._katanki_statistics = SimpleNamespace(reload=Mock())
    panel = module.PersonalTargetListsPanel(owner)
    yield SimpleNamespace(
        host=host,
        module=module,
        panel=panel,
        store=store,
        owner=owner,
        root=tmp_path,
        changed=host.window._katanki_statistics.reload,
    )
    panel.close()
    sys.modules.pop("katanki.ui.target_lists", None)


def import_file(context, monkeypatch, value):
    path = context.root / "import.json"
    path.write_text(value.to_json(), encoding="utf-8")
    monkeypatch.setattr(context.module.QFileDialog, "getOpenFileName", lambda *_: (str(path), ""))
    return path


def modal_action(context, label, *, before=None):
    """Click the real dialog button and retain the exact plain-text preview."""
    seen = []

    def act():
        dialog = context.host.app.activeModalWidget()
        assert dialog is not None
        previews = dialog.findChildren(context.module.QPlainTextEdit)
        if previews:
            seen.append(previews[0].toPlainText())
        if before:
            before()
        buttons = dialog.findChildren(context.module.QPushButton)
        next(button for button in buttons if button.text() == label).click()

    context.host.qt.QTimer.singleShot(0, act)
    return seen


def test_import_cancel_confirm_unchanged_and_replacement_diff(panel_host, monkeypatch):
    context = panel_host
    panel = context.panel
    assert not panel.export_button.isEnabled()
    assert "No personal list selected" in panel.details.toPlainText()
    first = target()
    import_file(context, monkeypatch, first)
    preview = modal_action(context, "Cancel")
    panel.import_button.click()
    assert not context.store.load()
    assert "Added kanji: 2" in preview[0]
    assert "My <kanji> list" in preview[0]  # Imported text stays literal.
    assert "Source SHA-256: " + "a" * 64 in preview[0]
    modal_action(context, "Import list")
    panel.import_button.click()
    assert context.store.load() == (first,)
    assert panel.export_button.isEnabled() and panel.remove_button.isEnabled()
    assert context.changed.call_count == 1
    stored = next(context.store.directory.glob("*.json"))
    original = stored.read_bytes(), stored.stat().st_mtime_ns
    preview = modal_action(context, "Replace existing list")
    panel.import_button.click()
    assert "Added kanji: 0" in preview[0] and "Removed kanji: 0" in preview[0]
    assert (stored.read_bytes(), stored.stat().st_mtime_ns) == original
    changed = replace(target("月火"), version="2")
    import_file(context, monkeypatch, changed)
    preview = modal_action(context, "Cancel")
    panel.import_button.click()
    assert context.store.load() == (first,)
    assert "Replaces: My <kanji> list (version 1)" in preview[0]
    assert "Added: 火" in preview[0] and "Removed: 日" in preview[0]
    modal_action(context, "Replace existing list")
    panel.import_button.click()
    assert context.store.load() == (changed,)
    assert "Version: 2" in panel.details.toPlainText()
    assert context.changed.call_count == 3


def test_export_and_remove_require_explicit_confirmation(panel_host, monkeypatch):
    context = panel_host
    path = import_file(context, monkeypatch, target())
    context.store.install(context.store.preview(path))
    context.panel._reload()
    output = context.root / "export.json"
    monkeypatch.setattr(context.module.QFileDialog, "getSaveFileName", lambda *_: ("", ""))
    context.panel.export_button.click()
    assert not output.exists()
    monkeypatch.setattr(context.module.QFileDialog, "getSaveFileName", lambda *_: (str(output), ""))
    context.panel.export_button.click()
    assert output.read_text(encoding="utf-8") == target().to_json()
    assert "Exported" in context.panel.status.text()
    modal_action(context, "Cancel")
    context.panel.remove_button.click()
    assert context.store.load() == (target(),)
    assert not context.changed.called
    modal_action(context, "Remove list")
    context.panel.remove_button.click()
    assert not context.store.load()
    assert not context.panel.export_button.isEnabled()
    assert not context.panel.remove_button.isEnabled()
    assert context.changed.call_count == 1
    context.panel._export()  # No selection stays harmless when invoked programmatically.
    context.panel._remove()


def test_invalid_input_and_reserved_ids_do_not_open_review(panel_host, monkeypatch):
    context = panel_host
    path = import_file(context, monkeypatch, target(list_id="reserved"))
    review = Mock(side_effect=AssertionError("Invalid imports must not reach review"))
    monkeypatch.setattr(context.panel, "_review", review)
    context.panel.import_button.click()
    assert "reserved by a dataset" in context.panel.status.text()
    path.write_text("invalid JSON", encoding="utf-8")
    context.panel.import_button.click()
    assert "Import failed:" in context.panel.status.text()
    assert not context.store.load()
    assert not review.called
    monkeypatch.setattr(context.module.QFileDialog, "getOpenFileName", lambda *_: ("", ""))
    context.panel.import_button.click()
    assert not review.called


@pytest.mark.parametrize("guard", ["busy", "profile"])
def test_guards_before_and_after_import_review(panel_host, monkeypatch, guard):
    context = panel_host
    import_file(context, monkeypatch, target())

    def deactivate():
        if guard == "busy":
            context.owner.busy = True
        else:
            context.owner.mw.col = None

    modal_action(context, "Import list", before=deactivate)
    context.panel.import_button.click()
    assert not context.store.load()
    assert not context.changed.called
    unexpected = Mock(side_effect=AssertionError("Inactive panel must not open a file picker"))
    monkeypatch.setattr(context.module.QFileDialog, "getOpenFileName", unexpected)
    context.panel._import()
    context.panel._export()
    context.panel._remove()
    assert not unexpected.called


def test_export_and_remove_failures_remain_visible(panel_host, monkeypatch):
    context = panel_host
    path = import_file(context, monkeypatch, target())
    context.store.install(context.store.preview(path))
    context.panel._reload()
    monkeypatch.setattr(
        context.module.QFileDialog, "getSaveFileName", lambda *_: (str(context.root), "")
    )
    context.panel.export_button.click()
    assert "Export failed:" in context.panel.status.text()

    def cannot_remove(_):
        raise OSError("permission denied")

    monkeypatch.setattr(context.store, "remove", cannot_remove)
    modal_action(context, "Remove list")
    context.panel.remove_button.click()
    assert "Remove failed: permission denied" in context.panel.status.text()
    assert context.store.load() == (target(),)
    assert not context.changed.called


def test_profile_switch_during_removal_prevents_write(panel_host, monkeypatch):
    context = panel_host
    path = import_file(context, monkeypatch, target())
    context.store.install(context.store.preview(path))
    context.panel._reload()
    modal_action(context, "Remove list", before=lambda: setattr(context.owner.mw, "col", None))
    context.panel.remove_button.click()
    assert context.store.load() == (target(),)
    assert not context.changed.called


def test_unavailable_profile_disables_import(panel_host):
    context = panel_host
    context.owner.mw.col = None
    panel = context.module.PersonalTargetListsPanel(context.owner)
    assert not panel.import_button.isEnabled()
    assert not panel.export_button.isEnabled()
    assert not panel.remove_button.isEnabled()
    assert panel.status.text() == "Open an Anki profile to manage personal lists."
    panel._import()
    panel.close()
