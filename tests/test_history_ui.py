import importlib
from datetime import date

from test_statistics_ui import qt_host as qt_host

from katanki.stats.history import ReviewEvidence


def test_native_history_window_modes_empty_rates_and_cleanup(qt_host, monkeypatch):
    host = qt_host
    module = importlib.import_module("katanki.ui.history")
    stamp = int(__import__("time").time() * 1000)
    reviews = (
        ReviewEvidence(stamp, "日", "recognition", 1, 1, 10),
        ReviewEvidence(stamp + 1, "日", "recognition", 3, 1, 10),
    )
    monkeypatch.setattr(module, "read_history", lambda col: (reviews, ("Fixture warning",)))
    dialog = module.HistoryDialog(host.window)
    host.operations[-1].complete()
    assert dialog.table.rowCount() == 90
    assert dialog.table.item(0, 0).text() == str(date.today())
    assert dialog.table.item(0, 4).text() == "0 / 1"
    assert dialog.table.item(0, 5).text() == "0.0%"
    assert dialog.table.item(1, 5).text() == "—"
    assert "Fixture warning" in dialog.status.text()
    assert not dialog.progress_chart.grab().isNull()
    assert not dialog.retention_chart.grab().isNull()
    dialog.period.setCurrentIndex(2)
    assert dialog.table.rowCount() == 1
    dialog.mode.setCurrentIndex(1)
    assert dialog.table.rowCount() == 0
    assert "No answered" in dialog.status.text()
    dialog.failed(ValueError("offline"))
    assert "offline" in dialog.status.text()
    dialog.close()
    assert dialog.closed and dialog.close not in host.hooks.profile_will_close
    dialog.loaded((reviews, ()))
    dialog.render()
    dialog.failed(ValueError("late"))
    module = __import__("sys").modules.pop("katanki.ui.history")


def test_history_late_load_does_not_cross_collection(qt_host):
    import sys

    module = importlib.import_module("katanki.ui.history")
    dialog = module.HistoryDialog(qt_host.window)
    qt_host.window.col = object()
    dialog.loaded(((), ()))
    assert dialog.status.text() == "Loading review evidence…"
    dialog.done(0)
    assert dialog.closed
    sys.modules.pop("katanki.ui.history")
