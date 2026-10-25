"""Native read-only Parts statistics, isolated from kanji mastery."""

from aqt import gui_hooks
from aqt.operations import QueryOp
from aqt.qt import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..anki.primitive_statistics import primitive_snapshot
from ..stats.progress import STATES


class PrimitiveStatisticsDialog(QDialog):
    def __init__(self, mw):
        super().__init__(mw)
        self.mw, self.collection, self.snapshot = mw, mw.col, None
        self.active = True
        self.setWindowTitle("Katanki — Parts statistics")
        self.resize(800, 600)
        layout = QVBoxLayout(self)
        description = QLabel(
            "Graphical components from enabled target lists and owned Parts notes. "
            "Parts evidence is independent of kanji mastery. Missing means no supported card; "
            "notes without cards are shown separately."
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        controls = QHBoxLayout()
        self.mode = QComboBox()
        self.mode.addItem("Recognition", "recognition")
        self.mode.addItem("Writing", "writing")
        self.mode.setAccessibleName("Parts study mode")
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search component label or key")
        self.search.setAccessibleName("Search components")
        self.refresh = QPushButton("Refresh")
        for control in (self.mode, self.search, self.refresh):
            controls.addWidget(control)
        layout.addLayout(controls)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Component", "Identity", "State", "Notes", "Cards"])
        self.table.setAccessibleName("Parts progress")
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True)
        layout.addWidget(self.table)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.mode.currentIndexChanged.connect(self.render)
        self.search.textChanged.connect(self.render)
        self.refresh.clicked.connect(self.reload)
        gui_hooks.profile_will_close.append(self.close)
        self.finished.connect(self.cleanup)
        self.reload()

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)

    def cleanup(self, *_):
        if self.active:
            self.active = False
            gui_hooks.profile_will_close.remove(self.close)

    def valid(self):
        return self.active and self.mw.col is self.collection

    def reload(self):
        if not self.valid() or not self.refresh.isEnabled():
            return
        self.refresh.setEnabled(False)
        self.status.setText("Loading graphical components and Parts cards…")
        QueryOp(parent=self.mw, op=primitive_snapshot, success=self.loaded).failure(
            self.failed
        ).run_in_background()

    def failed(self, error):
        if self.valid():
            self.refresh.setEnabled(True)
            self.status.setText(f"Could not load Parts statistics: {error}")

    def loaded(self, snapshot):
        if self.valid():
            self.snapshot = snapshot
            self.refresh.setEnabled(True)
            self.render()

    def render(self, *_):
        if self.snapshot is None:
            return
        progress, labels, warnings = self.snapshot
        mode, query = self.mode.currentData(), self.search.text().casefold().strip()
        rows = progress.payload(tuple(labels))["rows"]
        counts = progress.payload(tuple(labels))["counts"][mode]
        self.summary.setText(
            f"{len(labels)} unique components · "
            + " · ".join(f"{state.title()}: {counts[state]}" for state in STATES)
        )
        rows = [
            row
            for row in rows
            if query in (row["character"] + " " + labels[row["character"]]).casefold()
        ]
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            key = row["character"]
            details = progress.details(key)[mode]
            values = (
                labels[key],
                key,
                row[mode].title(),
                str(len(details["note_ids"])),
                str(len(details["cards"])),
            )
            for column, value in enumerate(values):
                self.table.setItem(index, column, QTableWidgetItem(value))
        self.table.setSortingEnabled(True)
        self.table.resizeColumnsToContents()
        self.status.setText(
            "\n".join(warnings) or "Read-only snapshot. Refresh after collection changes."
        )


def open_primitive_statistics(mw):
    dialog = getattr(mw, "_katanki_primitive_statistics", None)
    if dialog is None or not dialog.valid():
        dialog = PrimitiveStatisticsDialog(mw)
        mw._katanki_primitive_statistics = dialog
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
