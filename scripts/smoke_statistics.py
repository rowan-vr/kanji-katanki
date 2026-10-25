"""Verify native Qt statistics, list/grade coverage and read-only Anki evidence."""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


def fixture(collection):
    from katanki.anki.identities import MODEL_MARKER

    ids = {}
    for mode, values in (
        ("recognition", (("日", 2, 30), ("日", 0, 0), ("月", 2, 20), ("火", 3, 30), ("景", 2, 21))),
        ("production", (("日", 1, 0), ("月", 2, 30))),
    ):
        model = collection.models.new(f"Statistics {mode}")
        model[MODEL_MARKER] = f"kanji-{mode}"
        collection.models.add_field(model, collection.models.new_field("Character"))
        template = collection.models.new_template("Card")
        template.update(qfmt="{{Character}}", afmt="{{FrontSide}}")
        collection.models.add_template(model, template)
        collection.models.add(model)
        for character, kind, interval in values:
            note = collection.new_note(model)
            note["Character"] = character
            collection.add_note(note, 1)
            card = note.cards()[0]
            card.type, card.ivl = kind, interval
            card.queue = -1 if character == "火" else {0: 0, 1: 1, 2: 2, 3: 1}[kind]
            card.reps = 5 if kind else 0
            collection.update_card(card)
            ids[(mode, character)] = card.id
    # Native vocabulary cards never imply kanji recognition or writing mastery.
    note = collection.new_note(collection.models.by_name("Basic"))
    note["Front"] = "色"
    collection.add_note(note, 1)
    cid = ids[("recognition", "景")]
    for offset, rating in enumerate((0, 1, 3)):
        collection.db.execute(
            "insert into revlog values(?,?,?,?,?,?,?,?,?)",
            1700000000000 + offset,
            cid,
            0,
            rating,
            21,
            20,
            2500,
            1000,
            1,
        )


def wait_for(predicate):
    from aqt.qt import QEventLoop, QTimer

    if predicate():
        return
    loop = QEventLoop()
    poll, deadline = QTimer(), QTimer()
    poll.timeout.connect(lambda: loop.quit() if predicate() else None)
    deadline.setSingleShot(True)
    deadline.timeout.connect(loop.quit)
    poll.start(20)
    deadline.start(10_000)
    loop.exec()
    poll.stop()
    deadline.stop()
    assert predicate(), "Timed out waiting for native statistics"


def choose_character(dialog, character):
    source_index = next(
        index for index, row in enumerate(dialog.source.rows) if row["character"] == character
    )
    dialog.grid.setCurrentIndex(dialog.proxy.mapFromSource(dialog.source.index(source_index, 0)))
    wait_for(
        lambda: dialog.detail_data is not None and dialog.detail_data["character"] == character
    )


def exercise_dashboard(mw):
    """Actual QueryOp, menu/window lifecycle, and native widgets in packaged Anki."""
    from katanki.ui.dashboard import open_statistics

    open_statistics(mw)
    dialog = mw._katanki_statistics
    wait_for(lambda: dialog.snapshot is not None and not dialog.loading)
    from katanki.ui.statistics_widgets import StateSwatch

    assert dialog.scope.headerItem().text(1) == "Known / targets"
    assert {s.state for s in dialog.findChildren(StateSwatch)} == {
        "missing",
        "new",
        "learning",
        "young",
        "mature",
        "relearning",
    }
    assert not hasattr(dialog, "web")
    dialog.select_scope(("joyo", None))
    assert dialog.source.rowCount() == 2136
    dialog.select_scope(("school-grades", "grade-1"))
    assert dialog.source.rowCount() == 80
    assert len([key for key in dialog.section_items if key[0] == "school-grades"]) == 7
    dialog.select_scope(("", None))
    choose_character(dialog, "景")
    original = dialog
    open_statistics(mw)
    assert mw._katanki_statistics is original
    wait_for(lambda: not dialog.loading)
    dialog.close()
    assert dialog.closed and not dialog.strokes.timer.isActive()
    print("PASS: packaged native Qt statistics, per-grade coverage, details, singleton and cleanup")


class InlineQuery:
    """Standalone widget smoke uses native collection APIs without Anki's main loop."""

    def __init__(self, *, parent, op, success):
        self.parent, self.op, self.success = parent, op, success
        self.failed = lambda error: (_ for _ in ()).throw(error)

    def failure(self, failed):
        self.failed = failed
        return self

    def run_in_background(self):
        try:
            result = self.op(self.parent.col)
        except Exception as error:
            self.failed(error)
        else:
            self.success(result)


def native_checks(mw, app):
    from aqt.qt import QColor, QEventLoop, QPalette, QTimer

    from katanki.ui.dashboard import open_statistics

    open_statistics(mw)
    dialog = mw._katanki_statistics
    wait_for(lambda: dialog.snapshot is not None)
    from katanki.ui.statistics_widgets import StateSwatch

    assert dialog.scope.headerItem().text(1) == "Known / targets"
    assert {s.state for s in dialog.findChildren(StateSwatch)} == {
        "missing",
        "new",
        "learning",
        "young",
        "mature",
        "relearning",
    }
    assert not hasattr(dialog, "web")
    dialog.select_scope(("joyo", None))
    assert dialog.count_labels["total"].text() == "2,136"
    assert dialog.counts["mature"] == 1
    assert dialog.counts["new"] == 1

    def visible_rows():
        return [
            dialog.proxy.index(i, 0).data(Qt.ItemDataRole.UserRole)
            for i in range(dialog.proxy.rowCount())
        ]

    from aqt.qt import Qt

    order = ("mature", "young", "relearning", "learning", "new", "missing")

    def assert_state_order(mode):
        ranks = [order.index(row[mode]) for row in visible_rows()]
        assert ranks == sorted(ranks)

    assert dialog.sort_by.currentData() == "state"
    assert_state_order("recognition")
    dialog.sort_by.setCurrentIndex(dialog.sort_by.findData("list"))
    assert [row["character"] for row in visible_rows()] == [
        row["character"] for row in dialog.source.rows
    ]
    dialog.sort_by.setCurrentIndex(dialog.sort_by.findData("state"))
    assert dialog.sort_by.count() == 2
    dialog.select_scope(("@cards", None))
    assert set(dialog.current_targets) == {"日", "月", "火", "景"}
    assert dialog.count_labels["total"].text() == "4"
    assert dialog.counts["missing"] == 0
    dialog.mode.setCurrentIndex(dialog.mode.findData("writing"))
    assert dialog.counts["missing"] == 2
    dialog.mode.setCurrentIndex(dialog.mode.findData("recognition"))
    dialog.select_scope(("joyo", None))
    school = [section for section in dialog.sections if section.key[0] == "school-grades"]
    assert [section.key[1] for section in school] == [None, *[f"grade-{i}" for i in range(1, 7)]]
    g1 = dialog.section_items[("school-grades", "grade-1")]
    g2 = dialog.section_items[("school-grades", "grade-2")]
    assert dialog.scope.itemWidget(g1, 1).maximum() == 80
    assert dialog.scope.itemWidget(g1, 1).value() == 1  # 月 is young.
    assert dialog.scope.itemWidget(g2, 1).value() == 0
    dialog.mode.setCurrentIndex(dialog.mode.findData("writing"))
    assert dialog.counts["mature"] == 1 and dialog.counts["missing"] == 2134
    assert_state_order("writing")
    assert g1.text(2) == "1"
    dialog.select_scope(("school-grades", "grade-1"))
    assert dialog.source.rowCount() == 80
    assert dialog.counts["learning"] == 1 and dialog.counts["mature"] == 1
    dialog.scope.blockSignals(True)
    dialog.scope.clearSelection()
    for grade in (1, 2, 3):
        dialog.section_items[("school-grades", f"grade-{grade}")].setSelected(True)
    dialog.scope.blockSignals(False)
    dialog._render_scope()
    assert dialog.source.rowCount() == 440
    dialog.state_filter.setCurrentIndex(dialog.state_filter.findData("mature"))
    assert dialog.proxy.rowCount() == 1
    dialog.search.setText("げつ")
    assert dialog.proxy.rowCount() == 1  # Kana-script-insensitive search matches ゲツ.
    dialog.search.clear()
    dialog.state_filter.setCurrentIndex(0)
    dialog.select_scope(("", None))
    dialog.search.setText("scenery")
    assert dialog.proxy.rowCount() == 1
    choose_character(dialog, "景")
    assert "No matching production note" in dialog.evidence_labels["writing"].text()
    assert "50% pass rate" in dialog.evidence_labels["recognition"].text()
    assert dialog.strokes.stroke_count == 12
    with patch(
        "katanki.ui.dashboard.dialogs.open", return_value=SimpleNamespace(search_for=Mock())
    ) as browser:
        dialog.browse_buttons["recognition"].click()
        query = browser.return_value.search_for.call_args.args[0]
        assert query.startswith("cid:") and " or " not in query
    dialog.play.click()
    assert dialog.strokes.timer.isActive()
    wait_for(lambda: dialog.strokes.frame > 0)
    dialog.reset.click()
    assert not dialog.strokes.timer.isActive()
    assert dialog.strokes.frame == dialog.strokes.stroke_count * 8
    dialog.search.clear()
    # Make the per-grade overview and native detail pane visible in the previews.
    dialog.select_scope(("school-grades", None))
    choose_character(dialog, "月")
    original_palette = app.palette()
    try:
        for width, dark in ((1280, False), (950, True)):
            palette = QPalette(original_palette)
            if dark:
                for role in (
                    QPalette.ColorRole.Window,
                    QPalette.ColorRole.Base,
                    QPalette.ColorRole.Button,
                ):
                    palette.setColor(role, QColor("#252d2e"))
                for role in (
                    QPalette.ColorRole.WindowText,
                    QPalette.ColorRole.Text,
                    QPalette.ColorRole.ButtonText,
                ):
                    palette.setColor(role, QColor("#e7eee9"))
                palette.setColor(QPalette.ColorRole.Highlight, QColor("#62b29e"))
            app.setPalette(palette)
            dialog.resize(width, 850)
            loop = QEventLoop()
            QTimer.singleShot(100, loop.quit)
            loop.exec()
            (ROOT / "dist").mkdir(exist_ok=True)
            dialog.grab().save(str(ROOT / f"dist/statistics-qt-{width}.png"))
    finally:
        app.setPalette(original_palette)
    # Verify the summary remains one surface under an opaque host stylesheet.
    from katanki.ui.statistics_widgets import OverviewBox

    for box in dialog.findChildren(OverviewBox):
        if box.state == "total":
            continue
        box.setStyleSheet("QWidget { background-color: #333333; }")
        app.processEvents()
        pixel = box.grab().toImage().pixelColor(8, box.height() - 8)
        assert pixel.name() != "#333333", f"Hidden overview tint: {box.state}"
        box.setStyleSheet("")
    dialog._changed(None, None)
    assert "Refresh" in dialog.status.text()
    dialog.refresh.click()
    wait_for(lambda: not dialog.loading)
    assert dialog.source.rowCount() == 1026
    assert "Snapshot:" in dialog.status.text()
    dialog.close()
    assert dialog.closed


def main():
    from anki.collection import Collection
    from aqt.qt import QApplication, QWidget

    app = QApplication.instance() or QApplication(["katanki-qt-statistics"])
    with TemporaryDirectory(prefix="katanki-statistics-") as directory:
        mw = QWidget()
        mw.col = Collection(str(Path(directory) / "collection.anki2"))
        try:
            fixture(mw.col)
            tables = ("notes", "cards", "revlog")
            before = {t: mw.col.db.all(f"select * from {t} order by id") for t in tables}
            with patch("katanki.ui.dashboard.QueryOp", InlineQuery):
                native_checks(mw, app)
            after = {t: mw.col.db.all(f"select * from {t} order by id") for t in tables}
            assert before == after
        finally:
            if hasattr(mw, "_katanki_statistics"):
                mw._katanki_statistics.close()
            mw.col.close()
            mw.close()
            app.processEvents()
    print(
        "PASS: Qt-only statistics, ordered grade coverage, native models/filtering/SVG, "
        "independent modes, details, lifecycle and unchanged collection"
    )


if __name__ == "__main__":
    main()
