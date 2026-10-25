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
