"""Per-category generation controls for the settings dialog."""

from aqt.qt import QCheckBox, QComboBox, QFormLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from ..config import GenerationSettings


class GenerationSettingsPanel(QWidget):
    def __init__(self, mw, category, settings):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        self.automatic = QCheckBox("Enable automatic generation")
        self.automatic.setChecked(settings.auto_generate)
        layout.addWidget(self.automatic)
        if category == "parts":
            help_text = "Generate recognition notes for graphical parts used by selected kanji."
        elif category == "production":
            help_text = "Practice writing from meanings and blanked vocabulary examples."
        else:
            help_text = "Practice recognizing the kanji found in your vocabulary."
        description = QLabel(
            help_text + " Enabled categories are selected when opening Generate; "
            "preview approval is still required."
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        form = QFormLayout()
        form.setVerticalSpacing(12)
        self.deck = QComboBox()
        self.deck.addItem("No deck — automatic generation disabled", None)
        for deck in mw.col.decks.all_names_and_ids():
            self.deck.addItem(deck.name, deck.id)
        if settings.target_deck_id is not None:
            index = self.deck.findData(settings.target_deck_id)
            if index < 0:
                self.deck.addItem("Missing deck — choose a replacement", settings.target_deck_id)
                index = self.deck.count() - 1
            self.deck.setCurrentIndex(index)
        self.deck.currentIndexChanged.connect(self._update_generation)
        self._update_generation()
        form.addRow("Target deck", self.deck)
        self.tags = QLineEdit(" ".join(settings.default_tags))
        self.tags.setPlaceholderText("katanki Japanese::Kanji")
        form.addRow("Default tags", self.tags)
        self.copy_tags = QCheckBox("Copy tags from matching source notes")
        self.copy_tags.setChecked(settings.copy_source_tags)
        form.addRow("Source tags", self.copy_tags)
        self.patterns = QLineEdit(" ".join(settings.source_tag_patterns))
        self.patterns.setPlaceholderText("All source tags, or filter: source::NIJ::*")
        self.patterns.setEnabled(settings.copy_source_tags)
        self.copy_tags.toggled.connect(self.patterns.setEnabled)
        form.addRow("Tag filter", self.patterns)
        layout.addLayout(form)
        hint = QLabel(
            "Separate tags or filters with spaces. Leave the filter empty to copy all tags. "
            "A filter such as source::NIJ::* copies only matching child tags. "
            "Tags are copied from vocabulary containing the kanji; parts inherit those sources."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch()

    def _update_generation(self):
        has_deck = self.deck.currentData() is not None
        if not has_deck:
            self.automatic.setChecked(False)
        self.automatic.setEnabled(has_deck)

    def settings(self):
        return GenerationSettings(
            self.automatic.isChecked(),
            self.deck.currentData(),
            tuple(dict.fromkeys(self.tags.text().split())),
            self.copy_tags.isChecked(),
            tuple(dict.fromkeys(self.patterns.text().split())),
        )
