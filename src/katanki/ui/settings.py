"""Edit persistent vocabulary sources and safe generation defaults."""

from aqt.operations import QueryOp
from aqt.qt import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from aqt.utils import showWarning

from ..anki.collection import resolve_sources, selected_notes
from ..config import Settings, load_settings, save_settings
from ..generation.discovery import scan_notes
from .sources import SourceSelector


class SettingsDialog(QDialog):
    def __init__(self, mw):
        super().__init__(mw)
        self.mw = mw
        self.busy = False
        self.test_result = None
        settings = load_settings(mw.col)
        self.setWindowTitle("Katanki — Settings")
        self.setObjectName("katanki_settings")
        self.resize(820, 440)
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        discovery = QWidget()
        self.tabs.addTab(discovery, "Discovery")
        discovery_layout = QVBoxLayout(discovery)
        discovery_layout.setContentsMargins(16, 16, 16, 16)
        discovery_layout.setSpacing(14)
        description = QLabel("Choose where Katanki finds your vocabulary.")
        description.setWordWrap(True)
        discovery_layout.addWidget(description)
        self.sources = SourceSelector(mw)
        discovery_layout.addWidget(self.sources)
        self.sources.restore(settings.sources)
        hint = QLabel("Use * for all decks or Japanese::* for a pattern. Subdecks are included.")
        hint.setWordWrap(True)
        discovery_layout.addWidget(hint)
        test_row = QHBoxLayout()
        self.test_button = QPushButton("Test discovery")
        self.test_button.setToolTip("Try the current sources without saving settings")
        self.test_button.clicked.connect(self._test_discovery)
        test_row.addWidget(self.test_button)
        self.test_status = QLabel("Try these sources before saving.")
        self.test_status.setWordWrap(True)
        test_row.addWidget(self.test_status, 1)
        discovery_layout.addLayout(test_row)
        warning = None
        generation = QWidget()
        self.tabs.addTab(generation, "Generation")
        generation_layout = QVBoxLayout(generation)
        self.deck = QComboBox()
        self.deck.addItem("Choose a destination each time", None)
        for deck in mw.col.decks.all_names_and_ids():
            self.deck.addItem(deck.name, deck.id)
        if settings.destination_deck_id is not None:
            index = self.deck.findData(settings.destination_deck_id)
            if index < 0:
                self.deck.addItem("Saved destination is missing — choose a deck", -1)
                index = self.deck.count() - 1
                warning = "The saved destination deck was deleted. Choose a destination."
            self.deck.setCurrentIndex(index)
        generation_layout.addWidget(QLabel("Default destination for new cards:"))
        generation_layout.addWidget(self.deck)
        self.primitives = QCheckBox("Include graphical component recognition prerequisites")
        self.primitives.setChecked(settings.include_primitives)
        generation_layout.addWidget(self.primitives)
        note = QLabel(
            "Production stays opt-in for each character/component. "
            "Saving settings does not generate cards or approve a preview."
        )
        note.setWordWrap(True)
        generation_layout.addWidget(note)
        generation_layout.addStretch()
        self.status = QLabel(warning or "")
        self.status.setWordWrap(True)
        self.status.setVisible(bool(warning))
        layout.addWidget(self.status)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self._save)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def _set_testing(self, busy):
        self.busy = busy
        self.sources.setEnabled(not busy)
        self.test_button.setEnabled(not busy)
        self.buttons.setEnabled(not busy)

    def _test_discovery(self):
        if self.busy:
            return
        try:
            rules = self.sources.rules()
        except ValueError as error:
            self.test_status.setText(str(error))
            return
        self.test_result = None
        self._set_testing(True)
        self.test_status.setText("Scanning current sources…")
        QueryOp(
            parent=self.mw,
            op=lambda collection: scan_notes(
                selected_notes(collection, resolve_sources(collection, rules))
            ),
            success=self._test_finished,
        ).failure(self._test_failed).with_progress("Katanki: test discovery").run_in_background()

    def _test_finished(self, result):
        self._set_testing(False)
        self.test_result = result
        self.test_status.setText(
            f"{result.scanned_notes:,} notes · {len(result.vocabulary):,} words · "
            f"{len(result.candidates):,} kanji candidates"
        )
        DiscoveryTestResults(self, result).exec()

    def _test_failed(self, error):
        self._set_testing(False)
        self.test_status.setText(f"Discovery test failed: {error}")

    def reject(self):
        # Keep this dialog and its callbacks alive until the read-only operation finishes.
        if not self.busy:
            super().reject()

    def _save(self):
        try:
            settings = Settings(
                self.sources.rules(), self.deck.currentData(), self.primitives.isChecked()
            )
            self.sources.selection()
            save_settings(self.mw.col, settings)
        except Exception as error:
            showWarning(f"Could not save Katanki settings:\n{error}", parent=self)
            return
        self.accept()


class DiscoveryTestResults(QDialog):
    def __init__(self, parent, result):
        super().__init__(parent)
        self.setWindowTitle("Katanki — Discovery test")
        self.setObjectName("katanki_discovery_test_results")
        self.resize(620, 480)
        layout = QVBoxLayout(self)
        summary = QLabel(
            f"Matched notes: {result.scanned_notes:,}\n"
            f"Unique vocabulary: {len(result.vocabulary):,} · "
            f"Unique kanji candidates: {len(result.candidates):,}"
        )
        summary.setWordWrap(True)
        layout.addWidget(summary)
        note = QLabel(
            "Tested the current source rows. Settings were not saved and no cards were changed."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        if not result.scanned_notes or not result.candidates:
            empty = QLabel(
                "No matching notes. Check your decks and note types."
                if not result.scanned_notes
                else "No kanji found. Check that the selected fields contain Japanese vocabulary."
            )
            empty.setWordWrap(True)
            layout.addWidget(empty)
        tabs = QTabWidget()
        for title, entries, separator in (
            ("Vocabulary", result.vocabulary, "\n"),
            ("Kanji candidates", result.candidates, " "),
        ):
            text = QTextEdit()
            text.setReadOnly(True)
            limit = 1000
            content = separator.join(entries[:limit]) or "None found."
            if len(entries) > limit:
                content += f"\n\nShowing the first {limit:,} of {len(entries):,}."
            text.setPlainText(content)
            tabs.addTab(text, title)
        layout.addWidget(tabs)
        explanation = QLabel(
            "Kanji candidates are extracted characters; dictionary support is not checked."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


def open_settings(mw):
    SettingsDialog(mw).exec()
