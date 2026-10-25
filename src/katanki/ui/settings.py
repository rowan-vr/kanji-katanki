"""Edit persistent vocabulary sources and safe generation defaults."""

from aqt.operations import QueryOp
from aqt.qt import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QTimer,
    QVBoxLayout,
    QWidget,
)
from aqt.utils import showWarning

from ..anki.collection import resolve_sources, selected_notes
from ..config import GENERATION_CATEGORIES, RefreshSettings, Settings, load_settings, save_settings
from ..dictionaries.preferences import dictionary_sources
from ..generation.discovery import scan_notes
from .card_settings import CardSettingsPanel
from .dictionaries import DictionarySettingsPanel
from .generation_settings import GenerationSettingsPanel
from .ignored import IgnoredCardsPanel
from .sources import SourceSelector
from .statistics import StatisticsSettingsPanel


class SettingsDialog(QDialog):
    def __init__(self, mw):
        super().__init__(mw)
        self.mw = mw
        self.busy = False
        self.test_result = None
        settings = load_settings(mw.col)
        self.original_cards = settings.cards
        self.cards_changed = False
        self.collection = mw.col
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
        description = QLabel(
            "Choose the Anki decks, note types and fields containing your Japanese words."
        )
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
        self.card_tabs = QTabWidget()
        self.tabs.addTab(self.card_tabs, "Cards")
        self.card_panels = {}
        for category in GENERATION_CATEGORIES:
            panel = CardSettingsPanel(category, settings.card_settings(category))
            self.card_panels[category] = panel
            self.card_tabs.addTab(panel, category.title())
        self.dictionary_panel = DictionarySettingsPanel(self, settings.dictionaries)
        self.tabs.addTab(self.dictionary_panel, "Dictionaries")
        self.statistics_panel = StatisticsSettingsPanel(self, settings.dictionaries)
        self.tabs.addTab(self.statistics_panel, "Statistics")
        self.dictionary_panel.automatic.toggled.connect(
            self.statistics_panel.lists.automatic.setChecked
        )
        self.statistics_panel.lists.automatic.toggled.connect(
            self.dictionary_panel.automatic.setChecked
        )
        self.ignored_panel = IgnoredCardsPanel(mw)
        self.tabs.addTab(self.ignored_panel, "Ignored cards")
        refresh_panel = QWidget()
        refresh_layout = QVBoxLayout(refresh_panel)
        refresh_layout.addWidget(QLabel("Card updates — manual and automatic refresh"))
        self.refresh_tags = QCheckBox("Update tags from source vocabulary")
        self.refresh_examples = QCheckBox("Update example words")
        self.refresh_dictionary = QCheckBox("Update dictionary data")
        self.refresh_dictionary.setToolTip(
            "Refresh dictionary-derived content on existing cards using the selected "
            "dictionaries. Dictionary pack downloads are managed under Dictionaries."
        )
        self.refresh_dictionary.setChecked(settings.refresh.update_dictionary_data)
        self.refresh_tags.setChecked(settings.refresh.update_source_tags)
        self.refresh_examples.setChecked(settings.refresh.update_examples)
        refresh_layout.addWidget(self.refresh_tags)
        refresh_layout.addWidget(self.refresh_examples)
        refresh_layout.addWidget(self.refresh_dictionary)
        update_hint = QLabel(
            "Example updates respect each category's refresh setting under Cards. "
            "Refresh overwrites Katanki-managed fields. "
            "Tag and dictionary-content updates remain planned."
        )
        update_hint.setWordWrap(True)
        refresh_layout.addWidget(update_hint)
        refresh_layout.addWidget(QLabel("Automatic refresh triggers"))
        self.refresh_enabled = QCheckBox("Enable automatic refresh")
        self.refresh_open = QCheckBox("When a profile opens")
        self.refresh_sync = QCheckBox("After sync completes")
        self.refresh_enabled.setChecked(settings.refresh.enabled)
        self.refresh_open.setChecked(settings.refresh.on_profile_open)
        self.refresh_sync.setChecked(settings.refresh.after_sync)
        for control in (self.refresh_enabled, self.refresh_open, self.refresh_sync):
            refresh_layout.addWidget(control)
        self.refresh_enabled.toggled.connect(self.refresh_open.setEnabled)
        self.refresh_enabled.toggled.connect(self.refresh_sync.setEnabled)
        self.refresh_open.setEnabled(settings.refresh.enabled)
        self.refresh_sync.setEnabled(settings.refresh.enabled)
        explanation = QLabel(
            "Automatic refresh waits for the deck list and uses your saved sources and "
            "generation choices. New cards still require approval in the creation review. "
            "New-card creation and existing-card updates use separate settings."
        )
        explanation.setWordWrap(True)
        refresh_layout.addWidget(explanation)
        refresh_layout.addStretch()
        self.tabs.addTab(refresh_panel, "Refresh")
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
        self.statistics_panel.setEnabled(not busy)
        if not busy:
            for section in (self.dictionary_panel, self.statistics_panel.lists):
                section._show_last_check()
                for panel in section.panels.values():
                    panel.refresh_updates()
        self.ignored_panel.setEnabled(not busy)

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
                self.dictionary_panel.choices() + self.statistics_panel.choices(),
                tuple(self.card_panels[category].settings() for category in GENERATION_CATEGORIES),
                RefreshSettings(
                    self.refresh_enabled.isChecked(),
                    self.refresh_open.isChecked(),
                    self.refresh_sync.isChecked(),
                    self.refresh_tags.isChecked(),
                    self.refresh_examples.isChecked(),
                    self.refresh_dictionary.isChecked(),
                ),
                load_settings(self.collection).statistics_selection,
            )
            dictionary_sources(settings.dictionaries)
            dictionary_sources(settings.dictionaries, capability="target_lists")
            self.sources.selection()
            for category in GENERATION_CATEGORIES:
                deck_id = settings.generation_settings(category).target_deck_id
                if deck_id is not None and self.mw.col.decks.get(deck_id, default=False) is None:
                    raise ValueError(
                        f"The {category} target deck is missing. Choose its replacement."
                    )
            save_settings(self.mw.col, settings)
            self.dictionary_panel.save_preferences()
        except Exception as error:
            showWarning(f"Could not save Katanki settings:\n{error}", parent=self)
            return
        self.cards_changed = settings.cards != self.original_cards
        self.accept()

    def exec(self):
        result = super().exec()
        if (
            result == QDialog.DialogCode.Accepted
            and self.cards_changed
            and self.mw.col is self.collection
        ):
            self._offer_refresh()
        return result

    def _offer_refresh(self):
        prompt = QMessageBox(self.mw)
        prompt.setObjectName("katanki_card_settings_refresh")
        prompt.setWindowTitle("Katanki — Apply card settings")
        prompt.setIcon(QMessageBox.Icon.Information)
        prompt.setText("Your card settings have been saved.")
        prompt.setInformativeText(
            "Refresh your cards to apply the changed settings. Refresh uses your saved "
            "update preferences and overwrites Katanki-managed fields. "
            "You can also do this later "
            "from Katanki → Refresh and generate Kanji Cards."
        )
        later = prompt.addButton("Do later", QMessageBox.ButtonRole.RejectRole)
        now = prompt.addButton("Refresh now", QMessageBox.ButtonRole.AcceptRole)
        prompt.setDefaultButton(later)
        prompt.setEscapeButton(later)
        prompt.exec()
        if prompt.clickedButton() is now:
            from .refresh import open_refresh

            QTimer.singleShot(
                0,
                lambda: open_refresh(self.mw) if self.mw.col is self.collection else None,
            )


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


def open_settings(mw, *, tab=None):
    dialog = SettingsDialog(mw)
    if tab is not None:
        for index in range(dialog.tabs.count()):
            if dialog.tabs.tabText(index) == tab:
                dialog.tabs.setCurrentIndex(index)
                break
    dialog.exec()
