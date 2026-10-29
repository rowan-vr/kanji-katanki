"""The optional reading choice follows the source note type and survives reopening."""

import importlib
import sys
from types import ModuleType, SimpleNamespace

from katanki.config import SourceRule


def test_optional_reading_selection_round_trip(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PyQt6 import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    monkeypatch.setitem(sys.modules, "aqt", ModuleType("aqt"))
    monkeypatch.setitem(sys.modules, "aqt.qt", QtWidgets)
    monkeypatch.delitem(sys.modules, "katanki.ui.sources", raising=False)
    sources = importlib.import_module("katanki.ui.sources")
    monkeypatch.setattr(
        sources,
        "scan_sources",
        lambda col: (
            [(10, "Words")],
            [(20, "Vocabulary", ("Expression", "Reading")), (21, "Other", ("Front",))],
        ),
    )
    mw = QtWidgets.QWidget()
    mw.col = SimpleNamespace()
    selector = sources.SourceSelector(mw)
    rule = SourceRule("", 20, ("Expression",), (10,), "Reading")
    selector.restore((rule,))
    assert selector.rules() == (rule,)
    row = selector.rows[0]
    row.types.setCurrentIndex(row.types.findData(21))
    assert row.reading.currentData() is None
    assert row.reading.count() == 2
    selector.close()
    mw.close()
    app.processEvents()
