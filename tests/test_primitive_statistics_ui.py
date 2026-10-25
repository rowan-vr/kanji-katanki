"""Real Qt dialog exercised with asynchronous collection boundary stubbed."""

import importlib
import sys

from test_statistics_ui import qt_host  # noqa: F401

from katanki.stats.progress import CardEvidence, ProgressSnapshot


def test_parts_dialog_modes_search_and_stale_profile(qt_host, monkeypatch):  # noqa: F811
    host = qt_host
    monkeypatch.delitem(sys.modules, "katanki.ui.primitive_statistics", raising=False)
    module = importlib.import_module("katanki.ui.primitive_statistics")
    progress = ProgressSnapshot(
        (CardEvidence("graph:key", "recognition", 1, 2, "mature", 30, 5, 0),),
        (("graph:key", "recognition", 2), ("empty", "recognition", 3)),
    )
    monkeypatch.setattr(
        module,
        "primitive_snapshot",
        lambda _: (
            progress,
            {"graph:key": "Graphical shape", "empty": "Empty part", "missing": "Missing"},
            (),
        ),
    )
    dialog = module.PrimitiveStatisticsDialog(host.window)
    host.operations[-1].complete()
    assert dialog.table.rowCount() == 3
    assert "Mature: 1" in dialog.summary.text()
    dialog.search.setText("graph:key")
    assert dialog.table.rowCount() == 1
    dialog.mode.setCurrentIndex(1)
    assert dialog.table.item(0, 2).text() == "Missing"
    dialog.search.clear()
    assert "Missing: 3" in dialog.summary.text()
    dialog.reload()
    pending = host.operations[-1]
    dialog.close()
    pending.complete()
    assert not dialog.valid()
    assert not host.hooks.profile_will_close
    sys.modules.pop("katanki.ui.primitive_statistics", None)


def test_source_failure_retry_and_profile_switch_discard(qt_host, monkeypatch):  # noqa: F811
    host = qt_host
    monkeypatch.delitem(sys.modules, "katanki.ui.primitive_statistics", raising=False)
    module = importlib.import_module("katanki.ui.primitive_statistics")

    def unavailable(_):
        raise OSError("missing source")

    monkeypatch.setattr(module, "primitive_snapshot", unavailable)
    dialog = module.PrimitiveStatisticsDialog(host.window)
    host.operations[-1].complete()
    assert dialog.refresh.isEnabled()
    assert dialog.status.text() == "Could not load Parts statistics: missing source"
    dialog.reload()
    assert not dialog.refresh.isEnabled()
    pending_count = len(host.operations)
    dialog.reload()  # Avoid overlapping collection reads while loading.
    assert len(host.operations) == pending_count
    host.window.col = object()
    host.operations[-1].complete()
    assert not dialog.refresh.isEnabled()  # Stale callback did not mutate the window.
    dialog.loaded((ProgressSnapshot(()), {}, ()))
    assert dialog.snapshot is None
    dialog.close()
    sys.modules.pop("katanki.ui.primitive_statistics", None)


def test_parts_window_singleton_and_reopen_after_close(qt_host, monkeypatch):  # noqa: F811
    host = qt_host
    monkeypatch.delitem(sys.modules, "katanki.ui.primitive_statistics", raising=False)
    module = importlib.import_module("katanki.ui.primitive_statistics")
    module.open_primitive_statistics(host.window)
    original = host.window._katanki_primitive_statistics
    module.open_primitive_statistics(host.window)
    assert host.window._katanki_primitive_statistics is original
    assert len(host.operations) == 1
    original.close()
    module.open_primitive_statistics(host.window)
    replacement = host.window._katanki_primitive_statistics
    assert replacement is not original
    assert replacement.valid()
    assert len(host.operations) == 2
    replacement.close()
    sys.modules.pop("katanki.ui.primitive_statistics", None)
