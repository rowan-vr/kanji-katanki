"""Real Qt coverage for statistics, with only the Anki host boundary replaced."""

import importlib
import sys
from types import ModuleType, SimpleNamespace

import pytest

from katanki.stats.progress import CardEvidence, ProgressSnapshot
from katanki.stats.targets import TargetRegistry

SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
    '<path d="M10 10L90 90"/><path d="M90 10L10 90"/></svg>'
)


@pytest.fixture
def qt_host(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PyQt6 import QtCore, QtGui, QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    qt = ModuleType("aqt.qt")
    for module in (QtCore, QtGui, QtWidgets):
        for name in dir(module):
            if name.startswith("Q"):
                setattr(qt, name, getattr(module, name))
    hooks = SimpleNamespace(operation_did_execute=[], profile_will_close=[])
    searches = []
    aqt = ModuleType("aqt")
    aqt.gui_hooks = hooks
    aqt.dialogs = SimpleNamespace(open=lambda *args: SimpleNamespace(search_for=searches.append))
    operations = ModuleType("aqt.operations")

    class QueryOp:
        pending = []

        def __init__(self, *, parent, op, success):
            self.parent, self.op, self.success = parent, op, success
            self.pending.append(self)

        def failure(self, callback):
            self.failed = callback
            return self

        def without_collection(self):
            return self

        def with_progress(self, text):
            return self

        def run_in_background(self):
            pass

        def complete(self):
            try:
                result = self.op(self.parent.col)
            except Exception as error:
                self.failed(error)
            else:
                self.success(result)

    operations.QueryOp = QueryOp
    for name, module in (("aqt", aqt), ("aqt.qt", qt), ("aqt.operations", operations)):
        monkeypatch.setitem(sys.modules, name, module)
    names = ("statistics_widgets", "dashboard", "datasets", "statistics")
    for name in names:
        monkeypatch.delitem(sys.modules, f"katanki.ui.{name}", raising=False)
    modules = SimpleNamespace(
        **{name: importlib.import_module(f"katanki.ui.{name}") for name in names}
    )
    window = QtWidgets.QWidget()
    window.col = object()
    yield SimpleNamespace(
        app=app,
        qt=qt,
        modules=modules,
        window=window,
        hooks=hooks,
        operations=QueryOp.pending,
        searches=searches,
    )
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    app.processEvents()
    for name in names:
        sys.modules.pop(f"katanki.ui.{name}", None)


def snapshot():
    progress = ProgressSnapshot(
        (
            CardEvidence("日", "recognition", 1, 10, "mature", 30, 5, 1, True, True),
            CardEvidence("月", "writing", 2, 20, "young", 5, 2, 0),
        ),
        notes=(("月", "recognition", 30),),
        warnings=("Invalid note omitted",),
    )
    return (
        TargetRegistry(()),
        progress,
        {
            "日": {"meanings": ("sun",), "on": ("ニチ",), "kun": ("ひ",)},
            "月": {"meanings": ("moon",), "on": ("ゲツ",), "kun": ("つき",)},
        },
        ["No target lists"],
    )


def test_dashboard_scope_filters_details_and_lifecycle(qt_host, monkeypatch):
    host = qt_host
    module = host.modules.dashboard
    data = snapshot()
    monkeypatch.setattr(module, "dashboard_snapshot", lambda col: data)
    details = data[1].details("日")
    for evidence in details.values():
        evidence.update(answered=5, passed=4)
    monkeypatch.setattr(
        module,
        "character_details",
        lambda *args: {
            "character": "日",
            "evidence": details,
            "dictionary": data[2]["日"],
            "svg": SVG,
            "warnings": ["Example warning"],
        },
    )
    module.open_statistics(host.window)
    dialog = host.window._katanki_statistics
    host.app.processEvents()
    host.operations[-1].complete()
    dialog.select_scope(("@cards", None))
    assert dialog.source.rowCount() == 2
    assert dialog.count_labels["mature"].text() == "1"
    dialog.warning_button.setChecked(True)
    assert "Invalid note" in dialog.warnings.toPlainText()
    dialog.search.setText("SUN")
    assert dialog.proxy.rowCount() == 1
    dialog.grid.setCurrentIndex(dialog.proxy.index(0, 0))
    host.operations[-1].complete()
    assert dialog.definition.text() == "sun"
    assert "80%" in dialog.evidence_labels["recognition"].text()
    assert "Suspended" in dialog.evidence_labels["recognition"].text()
    dialog._browse("recognition")
    assert host.searches == ["cid:1"]
    dialog.play.click()
    assert dialog.strokes.timer.isActive()
    dialog.reset.click()
    assert not dialog.strokes.timer.isActive()
    dialog._detail_failed("日", ValueError("unavailable"))
    assert "unavailable" in dialog.definition.text()
    dialog._details_loaded({"character": "月"})  # stale response
    dialog.search.clear()
    dialog.mode.setCurrentIndex(1)
    assert dialog.count_labels["young"].text() == "1"
    dialog.state_filter.setCurrentIndex(dialog.state_filter.findData("mature"))
    assert dialog.proxy.rowCount() == 0
    assert "No kanji match" in dialog.empty.text()
    dialog.state_filter.setCurrentIndex(0)
    dialog.sort_by.setCurrentIndex(1)
    dialog.scope.clearSelection()
    assert dialog.source.rowCount() == 0
    dialog._changed(None, None)
    assert "Collection changed" in dialog.status.text()
    dialog._failed(ValueError("failed"))
    assert "failed" in dialog.status.text()
    module.open_statistics(host.window)
    assert host.window._katanki_statistics is dialog
    dialog.close()
    assert not host.hooks.operation_did_execute
    assert not host.hooks.profile_will_close
    dialog._loaded(data)
    dialog.reload()
    dialog.done(0)
    assert dialog.closed


def test_dashboard_missing_dictionary_notes_without_cards_and_stale_collection(qt_host):
    dialog = qt_host.modules.dashboard.StatisticsDialog(qt_host.window)
    dialog._loaded(snapshot())
    dialog.selected_character = "月"
    evidence = snapshot()[1].details("月")
    for item in evidence.values():
        item.update(answered=0, passed=0)
    dialog._details_loaded({"character": "月", "evidence": evidence, "warnings": []})
    assert "No dictionary" in dialog.definition.text()
    assert "has no cards" in dialog.evidence_labels["recognition"].text()
    dialog._browse("recognition")
    assert not qt_host.searches
    qt_host.window.col = object()
    dialog._choose_kanji(qt_host.qt.QModelIndex())
    assert dialog.selected_character is None
    dialog.close()


def test_models_accessibility_sorting_paint_and_stroke_playback(qt_host):
    qt, widgets = qt_host.qt, qt_host.modules.statistics_widgets
    model = widgets.KanjiModel()
    rows = snapshot()[1].payload(("日", "月"))["rows"]
    model.set_rows([row | snapshot()[2][row["character"]] for row in rows], "recognition")
    assert model.rowCount(model.index(0, 0)) == 0
    assert model.data(qt.QModelIndex()) is None
    for role in (qt.Qt.ItemDataRole.ToolTipRole, qt.Qt.ItemDataRole.AccessibleTextRole):
        assert "日" in model.data(model.index(0, 0), role)
    assert model.data(model.index(0, 0), qt.Qt.ItemDataRole.DecorationRole) is None
    proxy = widgets.KanjiFilter()
    proxy.setSourceModel(model)
    proxy.configure("", None, "recognition")
    assert proxy.index(0, 0).data() == "日"
    proxy.configure("ニチ", None, "recognition")
    assert proxy.rowCount() == 1
    proxy.configure("", "missing", "recognition", "list")
    assert proxy.index(0, 0).data() == "月"
    palette = qt.QPalette()
    palette.setColor(qt.QPalette.ColorRole.Base, qt.QColor("#111111"))
    assert widgets.state_colors("missing", palette)[0].name() == widgets.DARK["missing"]
    for state in ("total", "mature"):
        box = widgets.OverviewBox(state, state)
        box.setPalette(palette)
        box.grab()
    swatch = widgets.StateSwatch("new")
    assert not swatch.grab().isNull()
    parent = qt.QWidget()
    parent.source = model
    delegate = widgets.KanjiDelegate(parent)
    image = qt.QPixmap(100, 100)
    painter = qt.QPainter(image)
    option = qt.QStyleOptionViewItem()
    option.rect = qt.QRect(0, 0, 49, 52)
    option.state = qt.QStyle.StateFlag.State_Selected
    delegate.paint(painter, option, model.index(0, 0))
    delegate.paint(painter, option, qt.QModelIndex())
    painter.end()
    assert delegate.sizeHint(option, model.index(0, 0)).width() == 49
    stroke = widgets.StrokeDiagram()
    stroke.play()
    stroke.set_svg(SVG)
    assert stroke.renderer.isValid() and stroke.stroke_count == 2
    stroke.play()
    for _ in range(16):
        stroke._advance()
    assert not stroke.timer.isActive()
    assert not stroke.grab().isNull()
    stroke.changeEvent(qt.QEvent(qt.QEvent.Type.PaletteChange))
    stroke.reset()
    assert stroke.frame == 16
    stroke.set_svg(None)
    assert stroke.stroke_count == 0


@pytest.fixture
def dataset_host(qt_host, monkeypatch):
    module = qt_host.modules.datasets
    state = {"release": None, "installed": None, "preferences": {}}
    monkeypatch.setattr(module.updates, "installed", lambda manifest: state["installed"])
    monkeypatch.setattr(module.updates, "available", lambda *args: state["release"])
    monkeypatch.setattr(module.updates, "preferences", lambda: state["preferences"])
    owner = qt_host.window
    owner.mw, owner.busy = owner, False

    def set_testing(value):
        owner.busy = value

    owner._set_testing = set_testing
    return qt_host, module, state


@pytest.mark.parametrize("targets", (False, True))
def test_dataset_settings_source_choices_and_update_checks(dataset_host, monkeypatch, targets):
    from katanki.config import DictionaryChoice

    host, module, state = dataset_host
    panel = module.DatasetSettingsPanel(host.window, (), target_lists=targets)
    results = []
    monkeypatch.setattr(
        panel, "_show_result", lambda text, **kwargs: results.append((text, kwargs))
    )
    assert panel.panels
    assert all(
        ("target_lists" in p.manifest.capabilities) == targets for p in panel.panels.values()
    )
    assert "not been checked" in panel.update_status.text()
    saved = []
    monkeypatch.setattr(module.updates, "set_automatic", saved.append)
    panel.automatic.setChecked(True)
    panel.save_preferences()
    assert saved == [True]
    assert all(choice.mode == "bundled" for choice in panel.choices())
    state["preferences"] = {"last_success": 1700000000, "error": "offline"}
    panel._show_last_check()
    assert "Last attempt failed" in panel.update_status.text()
    monkeypatch.setattr(module.updates, "check_updates", lambda: {})
    panel._check_updates()
    assert host.window.busy
    host.operations[-1].complete()
    assert not host.window.busy and "up to date" in results[-1][0]
    state["release"] = {"version": "next"}
    first = next(iter(panel.panels.values()))
    first.mode.setCurrentIndex(first.mode.findData("disabled"))
    panel._checked({})
    assert "Default" in results[-1][0]
    assert len(results[-1][1]["candidates"]) == len(panel.panels) - 1
    panel._failed(OSError("offline"))
    assert "offline" in panel.update_status.text() and results[-1][1]["failed"]
    panel._install_failed(ValueError("bad archive"))
    assert "remain available" in results[-1][0]
    panel._installed([("One", "v2", ""), ("Two", "", "checksum mismatch")])
    assert "checksum mismatch" in results[-1][0] and results[-1][1]["failed"]
    panel._installed([("One", "v2", "")])
    assert "ready to use" in results[-1][0] and not results[-1][1]["failed"]
    monkeypatch.setattr(module.updates, "install", lambda *args: "v3")
    candidates = [(first.manifest, state["release"])]
    panel._install_updates(candidates)
    host.operations[-1].complete()
    assert "v3" in results[-1][0]

    def fail(*args):
        raise ValueError("invalid archive")

    monkeypatch.setattr(module.updates, "install", fail)
    panel._install_updates(candidates)
    host.operations[-1].complete()
    assert "invalid archive" in results[-1][0]
    host.window.busy = True
    count = len(host.operations)
    panel._check_updates()
    panel._install_updates(candidates)
    assert len(host.operations) == count
    with pytest.raises(ValueError, match="Unknown"):
        module.DatasetSettingsPanel(host.window, (DictionaryChoice("unknown"),))
    statistics = host.modules.statistics.StatisticsSettingsPanel(host.window, ())
    assert statistics.choices() == statistics.lists.choices()


@pytest.mark.parametrize("dataset_id", ("school-grades", "kanjidic2", "kanjivg", "jitendex"))
def test_dataset_checks_browsing_notices_and_update_outcomes(
    dataset_host, monkeypatch, tmp_path, dataset_id
):
    from katanki.config import DictionaryChoice

    host, module, state = dataset_host
    manifest = next(item for item in module.list_datasets() if item.id == dataset_id)
    panel = module.DatasetPanel(host.window, manifest, DictionaryChoice(dataset_id))
    panel.mode.setCurrentIndex(panel.mode.findData("local"))
    assert panel.path.isEnabled()
    monkeypatch.setattr(
        module.QFileDialog, "getOpenFileName", lambda *args: ("/tmp/local.json", "")
    )
    monkeypatch.setattr(module.QFileDialog, "getExistingDirectory", lambda *args: "/tmp/svg")
    panel._browse()
    assert panel.choice().path == "/tmp/local.json"
    panel._browse(True)
    assert panel.choice().path == "/tmp/svg"
    monkeypatch.setattr(module, "check_dictionary", lambda choice: "Validated fixture")
    panel._check()
    host.operations[-1].complete()
    assert panel.status.text() == "Check passed"
    assert panel.check_details.toPlainText() == "Validated fixture"
    panel._failed(ValueError("bad data"))
    assert not host.window.busy and "bad data" in panel.check_details.toPlainText()
    panel.mode.setCurrentIndex(panel.mode.findData("disabled"))
    panel._checked("disabled")
    assert panel.status.text() == "Disabled"
    panel._update()
    panel.mode.setCurrentIndex(panel.mode.findData("bundled"))
    panel._update()  # no compatible release
    state["release"] = {"version": "next"}
    monkeypatch.setattr(module.updates, "install", lambda *args: "next")
    panel._update()
    assert host.window.busy
    host.operations[-1].complete()
    assert panel.status.text() == "Installed next."
    panel._update_failed(ValueError("checksum"))
    assert "preserved" in panel.status.text()
    assert panel.check_details.toPlainText() == "checksum"
    monkeypatch.setattr(module.updates, "use_bundled", lambda *args: None)
    panel._use_bundled()
    assert panel.status.text() == "Using bundled defaults"

    def fail(*args):
        raise OSError("unreadable")

    monkeypatch.setattr(module.updates, "use_bundled", fail)
    panel._use_bundled()
    assert panel.status.text() == "unreadable"
    notice = tmp_path / "notice.html"
    notice.write_text("<p>Fixture attribution</p>")
    monkeypatch.setattr(module, "bundled_path", lambda *args: notice)
    panel.notice_files.addItem("fixture", "notice.html")
    panel.notice_files.setCurrentIndex(panel.notice_files.count() - 1)
    assert panel.notice.toPlainText().strip() == "Fixture attribution"
    state["installed"] = (tmp_path, {"bundled": manifest.bundled})
    panel.refresh_updates()
    assert panel.bundled_button.isEnabled()
    monkeypatch.setattr(module, "bundled_path", fail)
    panel._notice_changed()
    assert "Notice unavailable" in panel.notice.toPlainText()
    panel.notice_files.clear()
    assert panel.notice.toPlainText() == "No bundled notices."
    host.window.busy = True
    count = len(host.operations)
    panel._check()
    panel._update()
    panel._use_bundled()
    assert len(host.operations) == count
