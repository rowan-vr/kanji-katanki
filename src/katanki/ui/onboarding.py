"""Small first-run setup; advanced preferences remain in Settings."""

from dataclasses import replace

from aqt.qt import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QTabWidget,
    QTimer,
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage,
)
from aqt.utils import showInfo, showWarning

from ..anki.onboarding import COMPLETED_KEY
from ..config import CONFIG_KEY, GENERATION_CATEGORIES, load_settings, save_settings
from .sources import SourceSelector


def _page(title, description):
    page = QWizardPage()
    page.setTitle(title)
    layout = QVBoxLayout(page)
    label = QLabel(description)
    label.setWordWrap(True)
    layout.addWidget(label)
    return page, layout


class OnboardingDialog(QWizard):
    def __init__(self, mw):
        super().__init__(mw)
        self.mw = mw
        self.collection = mw.col
        self.saved = load_settings(self.collection)
        self._dismissed = False
        self.setObjectName("katanki_onboarding")
        self.setWindowTitle("Welcome to Katanki")
        self.resize(780, 540)
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage)
        self.setButtonText(QWizard.WizardButton.FinishButton, "Finish setup")

        page, layout = _page(
            "Welcome to Katanki!",
            "Learn the kanji behind the Japanese words you study. Katanki turns vocabulary "
            "from your Anki decks into kanji cards, with examples that connect back to your words.",
        )
        overview = QLabel(
            "Let's get you ready to study:\n\n"
            "1. Choose where your Japanese vocabulary lives.\n"
            "2. Decide which cards to create and whether to discover them automatically.\n"
            "3. Choose how your cards look.\n\n"
            "Already have kanji cards? You can choose to migrate them at the end of setup."
        )
        overview.setWordWrap(True)
        layout.addWidget(overview)
        hint = QLabel(
            "You only need the basics to get started. You can change your choices and "
            "explore more options later in Katanki → Settings."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch()
        self.addPage(page)

        page, layout = _page(
            "1. Choose your vocabulary",
            "Katanki finds kanji in your Japanese vocabulary. Choose a deck, its note type, "
            "and the field containing Japanese words (for example, Expression). "
            "Subdecks are included. You can add more sources later in Settings.",
        )
        self.sources = SourceSelector(mw)
        self.sources.restore(self.saved.sources)
        layout.addWidget(self.sources)
        self.manual_only = QCheckBox("I don't have vocabulary decks yet — set these up later")
        self.manual_only.toggled.connect(lambda checked: self.sources.setEnabled(not checked))
        layout.addWidget(self.manual_only)
        self.addPage(page)

        page, layout = _page(
            "2. Choose how to create cards",
            "Automatic generation discovers cards when you open Anki and after syncing. "
            "You review and approve new cards before they are created. "
            "You can also run Refresh and generate Kanji Cards from the Katanki menu anytime.",
        )
        types_group = QGroupBox("Which cards should Katanki prepare?")
        types_layout = QVBoxLayout(types_group)
        form = QFormLayout()
        self.categories = {}
        self.decks = {}
        for category, label in (
            ("recognition", "Recognition — read kanji"),
            ("production", "Production — write kanji"),
            ("parts", "Parts — learn kanji components"),
        ):
            choice = QCheckBox(label)
            saved = self.saved.generation_settings(category)
            choice.setChecked(saved.auto_generate)
            deck = QComboBox()
            deck.addItem("Choose a destination deck…", None)
            for entry in mw.col.decks.all_names_and_ids():
                deck.addItem(entry.name, entry.id)
            if saved.target_deck_id is not None:
                deck.setCurrentIndex(max(0, deck.findData(saved.target_deck_id)))
            deck.setEnabled(choice.isChecked())
            choice.toggled.connect(deck.setEnabled)
            form.addRow(choice, deck)
            self.categories[category] = choice
            self.decks[category] = deck
        types_layout.addLayout(form)
        hint = QLabel("Select each card type you want and choose its destination deck.")
        hint.setWordWrap(True)
        types_layout.addWidget(hint)
        layout.addWidget(types_group)
        timing_group = QGroupBox("When should Katanki check for these cards?")
        timing_layout = QVBoxLayout(timing_group)
        self.automatic = QCheckBox("Automatically when Anki opens and after syncing")
        self.automatic.setChecked(self.saved.refresh.enabled)
        timing_layout.addWidget(self.automatic)
        hint = QLabel(
            "Uses only the card types selected above. Leave this off to run discovery "
            "from the Katanki menu yourself. You approve new cards before creation."
        )
        hint.setWordWrap(True)
        timing_layout.addWidget(hint)
        layout.addWidget(timing_group)
        manual_hint = QLabel(
            "You can also add cards anytime from Katanki → New Kanji Cards: "
            "enter kanji yourself or choose a list, such as JLPT levels, Jōyō kanji, "
            "or school grades. No vocabulary deck is needed."
        )
        manual_hint.setWordWrap(True)
        layout.addWidget(manual_hint)
        layout.addStretch()
        self.addPage(page)

        page, layout = _page(
            "3. Make your cards comfortable to study",
            "Choose how your cards look. More options are available in Settings → Cards.",
        )
        self.appearance = {}
        card_tabs = QTabWidget()
        layout.addWidget(card_tabs)
        stored = self.collection.get_config(CONFIG_KEY, None)
        has_card_preferences = isinstance(stored, dict) and bool(stored.get("cards"))
        for category in GENERATION_CATEGORIES:
            saved = self.saved.card_settings(category)
            panel = QWidget()
            form = QFormLayout(panel)
            card_tabs.addTab(panel, category.title())
            if category == "parts":
                examples = QCheckBox("Show example kanji")
                examples.setChecked(saved.show_examples)
                name = QCheckBox("Show part names")
                name.setChecked(saved.show_name)
                form.addRow(examples)
                form.addRow(name)
                self.appearance[category] = (examples, name)
                continue
            if not has_card_preferences:
                saved = replace(
                    saved,
                    front_example_source="discovered",
                    example_source="discovered_and_default",
                    front_furigana=True,
                    furigana=True,
                )
            front = QComboBox()
            front.addItem("My vocabulary", "discovered")
            front.addItem("My vocabulary + dictionary words", "discovered_and_default")
            front.addItem("No examples", None)
            front.setCurrentIndex(
                front.findData(saved.front_source if saved.show_examples else None)
            )
            back = QComboBox()
            back.addItem("My vocabulary", "discovered")
            back.addItem("My vocabulary + dictionary words", "discovered_and_default")
            back.setCurrentIndex(back.findData(saved.example_source))
            front_furigana = QCheckBox("Show furigana on the front")
            front_furigana.setChecked(saved.front_furigana)
            back_furigana = QCheckBox("Show furigana on the back")
            back_furigana.setChecked(saved.furigana)
            form.addRow("Front examples", front)
            form.addRow("Back examples", back)
            form.addRow(front_furigana)
            form.addRow(back_furigana)
            self.appearance[category] = (front, back, front_furigana, back_furigana)
        self.migrate_existing = QCheckBox("Migrate my existing kanji cards after setup")
        layout.addWidget(self.migrate_existing)
        migration_hint = QLabel(
            "Already studying kanji? Choose your existing cards in the migration review. "
            "Migration preserves their scheduling and review history, then opens discovery."
        )
        migration_hint.setWordWrap(True)
        layout.addWidget(migration_hint)
        self.start_now = QCheckBox("Discover my first cards after setup")
        self.start_now.setChecked(True)
        layout.addWidget(self.start_now)
        self.migrate_existing.toggled.connect(
            lambda checked: self.start_now.setEnabled(not checked)
        )
        hint = QLabel(
            "Bundled dictionaries work offline. You can change these choices later in Settings."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch()
        self.addPage(page)
        self.manual_only.toggled.connect(self._defer_sources)

    def _defer_sources(self, deferred):
        if deferred:
            self.automatic.setChecked(False)
            self.start_now.setChecked(False)
            for choice in self.categories.values():
                choice.setChecked(False)

    def _rules(self):
        if self.manual_only.isChecked():
            return ()
        rules = self.sources.rules()
        self.sources.selection()
        return rules

    def _generation(self):
        generation = []
        for category in GENERATION_CATEGORIES:
            enabled = self.categories[category].isChecked()
            deck_id = self.decks[category].currentData()
            if enabled and (
                deck_id is None or self.collection.decks.get(deck_id, default=False) is None
            ):
                raise ValueError(f"Choose a destination deck for {category} cards.")
            generation.append(
                replace(
                    self.saved.generation_settings(category),
                    auto_generate=enabled,
                    target_deck_id=deck_id,
                )
            )
        if self.automatic.isChecked():
            if not any(item.auto_generate for item in generation):
                raise ValueError("Choose at least one card type for automatic generation.")
            if self.manual_only.isChecked():
                raise ValueError(
                    "Automatic discovery needs vocabulary sources. Go back to choose them."
                )
        return tuple(generation)

    def validateCurrentPage(self):
        try:
            if self.mw.col is not self.collection:
                raise ValueError("The Anki profile changed. Close setup and reopen it in Settings.")
            if self.currentId() == 1:
                self._rules()
            elif self.currentId() == 2:
                self._generation()
        except Exception as error:
            showWarning(str(error), parent=self)
            return False
        return True

    def reject(self):
        if self._dismissed or self.result() == QWizard.DialogCode.Accepted:
            return
        try:
            if self.mw.col is self.collection:
                self.collection.set_config(COMPLETED_KEY, True)
        except Exception as error:
            showWarning(f"Could not dismiss setup:\n{error}", parent=self)
            return
        self._dismissed = True
        showInfo(
            "You can restart setup anytime under Katanki → Settings → Refresh.\n\n"
            "Setup will not open automatically again. Your unsaved choices were discarded.",
            parent=self,
        )
        super().reject()

    def accept(self):
        try:
            if self.mw.col is not self.collection:
                raise ValueError("The Anki profile changed. Reopen setup in Settings.")
            cards = []
            for category in GENERATION_CATEGORIES:
                controls = self.appearance[category]
                if category == "parts":
                    examples, name = controls
                    changes = {"show_examples": examples.isChecked(), "show_name": name.isChecked()}
                else:
                    front, back, front_furigana, back_furigana = controls
                    saved_card = self.saved.card_settings(category)
                    front_source = front.currentData() or saved_card.front_example_source
                    if (
                        saved_card.front_example_source is None
                        and front.currentData() == saved_card.front_source
                        and back.currentData() == saved_card.example_source
                    ):
                        front_source = None
                    changes = {
                        "show_examples": front.currentData() is not None,
                        "front_example_source": front_source,
                        "example_source": back.currentData(),
                        "front_furigana": front_furigana.isChecked(),
                        "furigana": back_furigana.isChecked(),
                    }
                cards.append(replace(self.saved.card_settings(category), **changes))
            generation = self._generation()
            settings = replace(
                self.saved,
                sources=self._rules(),
                generation=generation,
                destination_deck_id=generation[0].target_deck_id,
                include_primitives=generation[2].auto_generate,
                cards=tuple(cards),
                refresh=replace(
                    self.saved.refresh,
                    enabled=self.automatic.isChecked(),
                    on_profile_open=True
                    if self.automatic.isChecked()
                    else self.saved.refresh.on_profile_open,
                    after_sync=True
                    if self.automatic.isChecked()
                    else self.saved.refresh.after_sync,
                ),
            )
            save_settings(self.collection, settings)
            self.collection.set_config(COMPLETED_KEY, True)
        except Exception as error:
            showWarning(f"Could not finish setup:\n{error}", parent=self)
            return
        super().accept()


def open_onboarding(mw):
    dialog = OnboardingDialog(mw)
    if dialog.exec() != QWizard.DialogCode.Accepted or mw.col is not dialog.collection:
        return
    if dialog.migrate_existing.isChecked():
        from .migration import open_migration

        collection = dialog.collection
        QTimer.singleShot(0, lambda: open_migration(mw) if mw.col is collection else None)
    elif dialog.start_now.isChecked() and not dialog.manual_only.isChecked():
        from .refresh import open_refresh

        collection = dialog.collection
        QTimer.singleShot(0, lambda: open_refresh(mw) if mw.col is collection else None)
