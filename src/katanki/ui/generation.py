"""Explicit per-character mode selection, read-only preview, then approval."""

import logging

from aqt.operations import CollectionOp, QueryOp
from aqt.qt import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    Qt,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
)
from aqt.utils import showInfo, showWarning

from ..anki.generation import apply_generation, preview_generation
from ..config import load_settings

logger = logging.getLogger(f"addon.{__name__}")


class GenerationDialog(QDialog):
    def __init__(self, mw, report):
        super().__init__(mw)
        self.mw, self.report = mw, report
        self.busy = False
        settings = load_settings(mw.col)
        self.setWindowTitle("Kanji Katanki — Generate independent cards")
        self.resize(800, 650)
        layout = QVBoxLayout(self)
        description = QLabel(
            "Check characters to generate recognition notes.\n"
            "Check production to practice writing from kanji meanings and blanked source words.\n"
            "Existing notes and progress are preserved. No vocabulary lifecycle tracking."
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        self.table = QTableWidget(len(report.scan.candidates), 3)
        self.table.setHorizontalHeaderLabels(["Character", "Recognition", "Production (opt-in)"])
        supported = {entry.character for entry in report.entries}
        for row, character in enumerate(report.scan.candidates):
            item = QTableWidgetItem(character)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, item)
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            check.setCheckState(
                Qt.CheckState.Checked if character in supported else Qt.CheckState.Unchecked
            )
            self.table.setItem(row, 1, check)
            production = QTableWidgetItem()
            production.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            production.setCheckState(Qt.CheckState.Unchecked)
            self.table.setItem(row, 2, production)
        self.table.horizontalHeader().setStretchLastSection(True)
        tabs = QTabWidget()
        tabs.addTab(self.table, "Kanji")
        component_entries = {}
        for visual in sorted(report.strokes, key=lambda entry: entry.character):
            for component in visual.component_entries:
                component_entries.setdefault(component.key, component)
        self.component_keys = sorted(component_entries)
        self.component_table = QTableWidget(len(self.component_keys), 4)
        self.component_table.setHorizontalHeaderLabels(
            ["Component", "Mnemonic name", "Recognition", "Production (opt-in)"]
        )
        for row, key in enumerate(self.component_keys):
            component = component_entries[key]
            item = QTableWidgetItem(component.label)
            item.setToolTip(key)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.component_table.setItem(row, 0, item)
            self.component_table.setItem(row, 1, QTableWidgetItem(""))
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            check.setCheckState(Qt.CheckState.Unchecked)
            self.component_table.setItem(row, 2, check)
            production = QTableWidgetItem()
            production.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            production.setCheckState(Qt.CheckState.Unchecked)
            self.component_table.setItem(row, 3, production)
        self.component_table.horizontalHeader().setStretchLastSection(True)
        tabs.addTab(self.component_table, "Graphical components")
        layout.addWidget(tabs)
        component_help = QLabel(
            "Components are graphical shapes, not dictionary radicals. "
            "Unencoded shapes require a mnemonic name in the components tab. "
            "Component production uses the supplied mnemonic name. "
            "Names apply to new notes only. Existing notes keep your edits."
        )
        component_help.setWordWrap(True)
        layout.addWidget(component_help)
        self.primitives = QCheckBox("Include graphical component recognition prerequisites")
        self.primitives.setChecked(settings.include_primitives)
        layout.addWidget(self.primitives)
        self.deck = QComboBox()
        for deck in mw.col.decks.all_names_and_ids():
            self.deck.addItem(deck.name, deck.id)
        self.deck.insertItem(0, "Choose a destination deck…", None)
        self.deck.setCurrentIndex(0)
        if settings.destination_deck_id is not None:
            index = self.deck.findData(settings.destination_deck_id)
            if index >= 0:
                self.deck.setCurrentIndex(index)
        layout.addWidget(QLabel("Destination deck for new cards:"))
        layout.addWidget(self.deck)
        self.status = QLabel(
            "Production examples come from the selected sources. Preview performs no writes."
        )
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        row = QHBoxLayout()
        layout.addLayout(row)
        self.preview_button = QPushButton("Preview generation…")
        self.preview_button.clicked.connect(self._preview)
        row.addWidget(self.preview_button)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        row.addWidget(close)

    def _set_busy(self, busy):
        self.busy = busy
        for widget in (
            self.table,
            self.component_table,
            self.primitives,
            self.deck,
            self.preview_button,
        ):
            widget.setEnabled(not busy)

    def _preview(self):
        recognition = []
        production = []
        for row in range(self.table.rowCount()):
            character = self.table.item(row, 0).text()
            if self.table.item(row, 1).checkState() == Qt.CheckState.Checked:
                recognition.append(character)
            if self.table.item(row, 2).checkState() == Qt.CheckState.Checked:
                production.append(character)
        component_names = {}
        primitive_recognition = []
        primitive_production = []
        for row, key in enumerate(self.component_keys):
            name = self.component_table.item(row, 1).text().strip()
            if name:
                component_names[key] = name
            if self.component_table.item(row, 2).checkState() == Qt.CheckState.Checked:
                primitive_recognition.append(key)
            if self.component_table.item(row, 3).checkState() == Qt.CheckState.Checked:
                primitive_production.append(key)
        if (
            not recognition
            and not production
            and not primitive_recognition
            and not primitive_production
        ):
            showWarning(
                "Select recognition or production for characters or components.", parent=self
            )
            return
        if self.deck.currentData() is None:
            showWarning("Select an existing destination deck.", parent=self)
            return
        deck_id, deck_name = self.deck.currentData(), self.deck.currentText()
        include_primitives = self.primitives.isChecked()
        self._set_busy(True)
        QueryOp(
            parent=self.mw,
            op=lambda collection: preview_generation(
                collection,
                self.report,
                recognition=tuple(recognition),
                production=tuple(production),
                include_primitives=include_primitives,
                component_names=component_names,
                primitive_recognition=tuple(primitive_recognition),
                primitive_production=tuple(primitive_production),
            ),
            success=lambda preview: self._confirm(preview, deck_id, deck_name),
        ).failure(self._failed).with_progress(
            "Kanji Katanki: generation preview"
        ).run_in_background()

    def _confirm(self, preview, deck_id, deck_name):
        self._set_busy(False)
        count = sum(item.outcome == "create" for item in preview.plan.items)
        dialog = QDialog(self)
        dialog.setWindowTitle("Review generation plan")
        dialog.resize(760, 600)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(f"Create {count} independent notes in deck: {deck_name}"))
        text = QTextEdit()
        text.setReadOnly(True)
        contents = {content.identity: content for content in preview.contents}
        lines = []
        for item in preview.plan.items:
            identity = item.unit.identity
            lines.append(
                f"{item.outcome.upper()}: {identity.key} [{identity.note_type}] — {item.reason}"
            )
            content = contents.get(identity)
            if content:
                lines.append(f"  Display/name: {content.display}")
                if content.prompt:
                    lines.append(f"  Production front:\n{content.prompt}")
                lines.append(f"  Meanings: {', '.join(content.meanings) or 'not supplied'}")
                lines.append(f"  Readings: {', '.join(content.readings) or 'not supplied'}")
                lines.append(
                    f"  Graphical components: {', '.join(content.components) or 'none listed'}"
                )
                lines.append(f"  Stroke diagram: {'available' if content.svg else 'unavailable'}")
        lines.extend(("", *preview.warnings, "", *self.report.provenance))
        text.setPlainText("\n".join(lines))
        layout.addWidget(text)
        layout.addWidget(QLabel("Existing notes are skipped. Cancel makes no changes."))
        row = QHBoxLayout()
        layout.addLayout(row)
        cancel = QPushButton("Cancel")
        cancel.setDefault(True)
        cancel.clicked.connect(dialog.reject)
        row.addWidget(cancel)
        approve = QPushButton(f"Approve and create {count} notes")
        approve.setEnabled(count > 0)
        approve.setAutoDefault(False)
        approve.clicked.connect(dialog.accept)
        row.addWidget(approve)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._set_busy(True)
        CollectionOp(
            parent=self.mw,
            op=lambda collection: apply_generation(collection, preview, deck_id=deck_id),
        ).success(self._applied).failure(self._failed).run_in_background()

    def _applied(self, result):
        self._set_busy(False)
        self.status.setText(
            f"Created {result.created} notes; skipped {result.skipped} newly existing notes."
        )
        showInfo(self.status.text() + " Existing notes and progress were preserved.", parent=self)
        self.accept()

    def _failed(self, error):
        self._set_busy(False)
        logger.error("Generation failed", exc_info=(type(error), error, error.__traceback__))
        self.status.setText("Operation stopped. Review the error before trying again.")
        showWarning(str(error), parent=self)

    def reject(self):
        if not self.busy:
            super().reject()
