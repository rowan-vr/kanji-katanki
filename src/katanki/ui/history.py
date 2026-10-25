"""Read-only native Qt history charts and accessible daily values."""

from datetime import date, timedelta

from aqt import gui_hooks
from aqt.operations import QueryOp
from aqt.qt import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPainter,
    QPen,
    QPointF,
    QRectF,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..anki.history import read_history
from ..stats.history import history_days

POLICY = (
    "Entire collection · Current Katanki kanji cards only · Local calendar days (midnight). "
    "Deleted cards/logs and past character or note-type changes cannot be recovered. "
    "Cumulative reviewed means unique kanji ever answered in available history, not mastery. "
    "Retention: first eligible scheduled review per kanji/day, previous interval ≥ 1 day; "
    "Hard/Good/Easy pass. Learning, relearning, filtered/cram and manual entries are excluded "
    "from retention. Recognition and writing are independent."
)


class HistoryChart(QWidget):
    """Small reusable line chart; None creates a gap, never a zero retention rate."""

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.title, self.points = title, ()
        self.setMinimumHeight(155)
        self.setAccessibleName(title)

    def set_points(self, points, maximum=None):
        self.points = tuple(points)
        self.maximum = maximum or max((p for p in self.points if p is not None), default=1) or 1
        self.setAccessibleDescription("Exact daily values are available in the table below.")
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(self.palette().text().color())
        painter.drawText(8, 20, self.title)
        area = QRectF(48, 32, max(1, self.width() - 64), max(1, self.height() - 58))
        maximum = getattr(self, "maximum", 1)
        painter.drawText(4, 43, f"{maximum:g}")
        painter.drawText(24, int(area.bottom()), "0")
        painter.drawRect(area)
        painter.setPen(QPen(self.palette().highlight().color(), 2))
        previous = None
        for index, value in enumerate(self.points):
            if value is None:
                previous = None
                continue
            point = QPointF(
                area.left() + index * area.width() / max(1, len(self.points) - 1),
                area.bottom() - value * area.height() / maximum,
            )
            if previous is not None:
                painter.drawLine(previous, point)
            painter.drawEllipse(point, 2, 2)
            previous = point


class HistoryDialog(QDialog):
    def __init__(self, mw):
        super().__init__(mw)
        self.mw, self.collection, self.closed = mw, mw.col, False
        self.reviews = ()
        self.setWindowTitle("Katanki — History")
        self.resize(960, 790)
        layout = QVBoxLayout(self)
        policy = QLabel(POLICY)
        policy.setWordWrap(True)
        layout.addWidget(policy)
        controls = QHBoxLayout()
        self.mode, self.period = QComboBox(), QComboBox()
        self.mode.addItem("Recognition", "recognition")
        self.mode.addItem("Writing", "writing")
        for title, days in (
            ("Last 90 days", 90),
            ("Last 365 days", 365),
            ("All available history", None),
        ):
            self.period.addItem(title, days)
        controls.addWidget(self.mode)
        controls.addWidget(self.period)
        layout.addLayout(controls)
        self.status = QLabel("Loading review evidence…")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress_chart = HistoryChart("Cumulative unique kanji reviewed")
        self.retention_chart = HistoryChart("Daily retention (%) · gaps mean no eligible tests")
        layout.addWidget(self.progress_chart)
        layout.addWidget(self.retention_chart)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            [
                "Local date",
                "Kanji answered",
                "First observed",
                "Cumulative",
                "Passed / tested",
                "Retention",
            ]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)
        self.mode.currentIndexChanged.connect(self.render)
        self.period.currentIndexChanged.connect(self.render)
        gui_hooks.profile_will_close.append(self.close)
        QueryOp(parent=mw, op=read_history, success=self.loaded).failure(
            self.failed
        ).run_in_background()

    def loaded(self, result):
        if self.closed or self.mw.col is not self.collection:
            return
        self.reviews, self.warnings = result
        self.render()

    def failed(self, error):
        if not self.closed:
            self.status.setText(f"History unavailable: {error}")

    def render(self):
        if self.closed:
            return
        end = date.today()
        length = self.period.currentData()
        start = end - timedelta(days=length - 1) if length else None
        rows = history_days(self.reviews, self.mode.currentData(), start=start, end=end)
        self.progress_chart.set_points([row.cumulative for row in rows])
        self.retention_chart.set_points([row.retention for row in rows], 100)
        self.table.setRowCount(len(rows))
        for index, row in enumerate(reversed(rows)):
            values = (
                str(row.day),
                str(row.answered),
                str(row.introduced),
                str(row.cumulative),
                f"{row.retained} / {row.tested}",
                f"{row.retention:.1f}%" if row.retention is not None else "—",
            )
            for column, value in enumerate(values):
                self.table.setItem(index, column, QTableWidgetItem(value))
        tested = sum(row.tested for row in rows)
        passed = sum(row.retained for row in rows)
        summary = f"{passed} / {tested} eligible kanji-days passed"
        if tested:
            summary += f" ({100 * passed / tested:.1f}%)"
        if rows:
            summary = f"{rows[0].day} – {rows[-1].day} · " + summary
        else:
            summary = "No answered review evidence for this mode."
        self.status.setText(summary + "\n" + "\n".join(getattr(self, "warnings", ())))

    def done(self, result):
        self._cleanup()
        super().done(result)

    def closeEvent(self, event):
        self._cleanup()
        super().closeEvent(event)

    def _cleanup(self):
        if not self.closed:
            self.closed = True
            gui_hooks.profile_will_close.remove(self.close)
