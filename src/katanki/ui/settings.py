"""Edit persistent vocabulary sources and safe generation defaults."""

from aqt.operations import QueryOp
from aqt.qt import (
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
from ..config import GENERATION_CATEGORIES, Settings, load_settings, save_settings
from ..dictionaries.preferences import dictionary_sources
from ..generation.discovery import scan_notes
from .dictionaries import DictionarySettingsPanel
from .generation_settings import GenerationSettingsPanel
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
        self.generation_tabs = QTabWidget()
        self.tabs.addTab(self.generation_tabs, "Generation")
        self.generation_panels = {}
        for category in GENERATION_CATEGORIES:
            panel = GenerationSettingsPanel(mw, category, settings.generation_settings(category))
            self.generation_panels[category] = panel
            self.generation_tabs.addTab(panel, category.title())
        # Retain the existing controls for integration harnesses and legacy defaults.
        self.deck = self.generation_panels["recognition"].deck
        self.primitives = self.generation_panels["parts"].automatic
        self.dictionary_panel = DictionarySettingsPanel(self, settings.dictionaries)
        self.tabs.addTab(self.dictionary_panel, "Dictionaries")
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
        self.dictionary_panel.setEnabled(not busy)

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
                self.sources.rules(),
                self.deck.currentData(),
                self.primitives.isChecked(),
                tuple(
                    self.generation_panels[category].settings()
                    for category in GENERATION_CATEGORIES
                ),
                self.dictionary_panel.choices(),
            )
            dictionary_sources(settings.dictionaries)
            self.sources.selection()
            for category in GENERATION_CATEGORIES:
                deck_id = settings.generation_settings(category).target_deck_id
                if deck_id is not None and self.mw.col.decks.get(deck_id, default=False) is None:
                    raise ValueError(
                        f"The {category} target deck is missing. Choose its replacement."
                    )
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
