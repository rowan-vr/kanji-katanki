"""Per-category card display preferences for the settings dialog."""

from dataclasses import replace

from aqt.qt import QCheckBox, QComboBox, QFormLayout, QLabel, QSpinBox, QVBoxLayout, QWidget


class CardSettingsPanel(QWidget):
    def __init__(self, category, settings):
        super().__init__()
        self.category = category
        self.saved_settings = settings
        parts = category == "parts"
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        description = QLabel(
            "Choose how parts cards display names and example kanji."
            if parts
            else f"Choose how {category} cards display example words."
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        form = QFormLayout()
        form.setVerticalSpacing(12)
        if parts:
            self.name = QCheckBox("Show the part's name on the front")
            self.name.setChecked(settings.show_name)
            form.addRow("Name", self.name)
        self.examples = QCheckBox(
            "Show example kanji containing the part on the back"
            if parts
            else "Show example words on the front"
        )
        self.examples.setChecked(settings.show_examples)
        form.addRow("Examples", self.examples)
        self.limit = QSpinBox()
        self.limit.setRange(0, 2_147_483_647)
        self.limit.setSpecialValueText("Show all")
        self.limit.setValue(settings.example_limit)
        self.limit.setToolTip(
            "Maximum examples displayed, including user examples. "
            "0 shows all. All eligible examples remain stored on the card."
        )
        form.addRow("Example limit", self.limit)
        self.source = QComboBox()
        if parts:
            self.source.addItem("Kanji from your vocabulary only", "discovered")
            self.source.addItem(
                "Kanji from your vocabulary + other kanji", "discovered_and_default"
            )
        else:
            self.source.addItem("Your vocabulary words only", "discovered")
            self.source.addItem(
                "Your vocabulary words + default examples", "discovered_and_default"
            )
            self.source.setToolTip(
                "Default examples from Jitendex are planned for a later release."
            )
        self.source.setCurrentIndex(self.source.findData(settings.example_source))
        form.addRow("Kanji sources" if parts else "Word sources", self.source)
        if not parts:
            self.furigana = QCheckBox("Show furigana on example words")
            self.furigana.setChecked(settings.furigana)
            form.addRow("Readings", self.furigana)
            self.word_status = QComboBox()
            self.word_status.addItem("Seen and new words", True)
            self.word_status.addItem("Seen words only", False)
            self.word_status.setCurrentIndex(self.word_status.findData(settings.include_new))
            self.word_status.setToolTip("Seen words have at least one source card reviewed before.")
            form.addRow("Vocabulary", self.word_status)
        self.refresh = QCheckBox(
            "Automatically refresh example kanji"
            if parts
            else "Automatically refresh example words"
        )
        self.refresh.setChecked(settings.auto_refresh)
        form.addRow("Refresh", self.refresh)
        layout.addLayout(form)
        sources_hint = QLabel(
            "Your vocabulary words come from the sources selected under Discovery."
        )
        sources_hint.setWordWrap(True)
        layout.addWidget(sources_hint)
        hint = QLabel(
            "These preferences are saved per category. Applying them to generated cards "
            "and automatically refreshing examples is planned for the card refresh work."
            + ("" if parts else " Default examples from Jitendex are planned for a later release.")
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch()

    def settings(self):
        changes = dict(
            show_examples=self.examples.isChecked(),
            example_source=self.source.currentData(),
            auto_refresh=self.refresh.isChecked(),
            example_limit=self.limit.value(),
        )
        if self.category == "parts":
            changes["show_name"] = self.name.isChecked()
        else:
            changes["furigana"] = self.furigana.isChecked()
            changes["include_new"] = self.word_status.currentData()
        return replace(self.saved_settings, **changes)
