"""Real Anki collection and Qt history smoke in an isolated temporary profile."""

import sys
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from scripts.smoke_statistics import InlineQuery, fixture  # noqa: E402


def main():
    from anki import buildinfo
    from anki.collection import Collection
    from aqt.qt import QApplication, QWidget

    from katanki.anki.history import read_history
    from katanki.stats.history import history_days
    from katanki.ui.history import HistoryDialog

    app = QApplication.instance() or QApplication(["katanki-history-smoke"])
    with TemporaryDirectory(prefix="katanki-history-") as directory:
        mw = QWidget()
        mw.col = Collection(str(Path(directory) / "collection.anki2"))
        try:
            fixture(mw.col)
            before = {
                t: mw.col.db.all(f"select * from {t} order by id")
                for t in ("notes", "cards", "revlog", "col")
            }
            events, warnings = read_history(mw.col)
            rows = history_days(events, "recognition", end=date.today())
            assert sum(row.tested for row in rows) == 1
            assert sum(row.retained for row in rows) == 0
            assert rows[-1].cumulative == 1
            with patch("katanki.ui.history.QueryOp", InlineQuery):
                dialog = HistoryDialog(mw)
            dialog.period.setCurrentIndex(2)
            assert dialog.table.rowCount() == len(rows)
            assert "0 / 1" in dialog.status.text()
            dialog.show()
            app.processEvents()
            assert not dialog.grab().isNull()
            dialog.mode.setCurrentIndex(1)
            assert dialog.table.rowCount() == 0
            dialog.close()
            assert dialog.closed
            after = {t: mw.col.db.all(f"select * from {t} order by id") for t in before}
            assert before == after
        finally:
            mw.col.close()
            mw.close()
            app.processEvents()
    print(
        f"PASS: Anki {buildinfo.version}, native Qt history, independent modes, "
        "first eligible answer retention, rendering/lifecycle and unchanged collection"
    )


if __name__ == "__main__":
    main()
