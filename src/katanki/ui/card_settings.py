"""Per-category example choices with separate question and answer sources."""

from dataclasses import replace

from aqt.qt import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QLabel,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


def _hint(text):
    label = QLabel(text)
    label.setWordWrap(True)
    return label


def _word_sources(value):
    choices = QComboBox()
    choices.addItem("Words from my selected Anki fields", "discovered")
    choices.addItem("My Anki words + Jitendex dictionary words", "discovered_and_default")
    choices.setCurrentIndex(choices.findData(value))
    choices.setToolTip(
        "My Anki words come from the decks, note types and fields selected under Discovery. "
        "Jitendex adds matching common words even when you have no Anki card for them."
    )
    return choices


class CardSettingsPanel(QWidget):
    def __init__(self, category, settings):
        super().__init__()
        self.category = category
        self.saved_settings = settings
        parts = category == "parts"
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)
        content = QWidget()
        scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)
        layout.addWidget(
            _hint(
                "Choose the examples used on the question and answer sides of these cards."
                if not parts
                else "Choose how graphical parts and their example kanji are displayed."
            )
        )

        front = QGroupBox("Question — front of card")
        front_form = QFormLayout(front)
        if parts:
            self.name = QCheckBox("Show the part's name")
            self.name.setChecked(settings.show_name)
            front_form.addRow(self.name)
        self.examples = QCheckBox(
            "Show example kanji containing the part on the back"
            if parts
            else "Show example words with the kanji"
            if category == "recognition"
            else "Show masked word clues"
        )
        self.examples.setChecked(settings.show_examples)
        if not parts:
            front_form.addRow(self.examples)
            self.front_source = _word_sources(settings.front_source)
            front_form.addRow("Examples on the front", self.front_source)
        self.limit = QSpinBox()
        self.limit.setRange(0, 2_147_483_647)
        self.limit.setSpecialValueText("All matching examples")
        self.limit.setValue(settings.example_limit)
        self.limit.setToolTip(
            "Limits question-side examples. "
            "The answer side keeps its full selected list."
        )
        if not parts:
            front_form.addRow("Maximum front examples", self.limit)
        if not parts:
            self.front_furigana = QCheckBox("Show readings below example words")
            self.front_furigana.setChecked(settings.front_furigana)
            front_form.addRow("Furigana", self.front_furigana)
        layout.addWidget(front)

        back = QGroupBox("Answer — back of card")
        back_form = QFormLayout(back)
        if parts:
            back_form.addRow(self.examples)
            self.source = QComboBox()
            self.source.addItem("Kanji found in my selected Anki fields", "discovered")
            self.source.addItem(
                "My selected kanji + other dictionary kanji", "discovered_and_default"
            )
            self.source.setCurrentIndex(self.source.findData(settings.example_source))
            back_form.addRow("Example kanji on the back", self.source)
            self.limit.hide()  # Preserve the saved legacy value; backs are not capped.
        else:
            self.back_source = _word_sources(settings.example_source)
            self.source = self.back_source
            back_form.addRow("Examples on the back", self.back_source)
        back_form.addRow(
            _hint(
                "All matching examples are available on the back. "
                "Long lists have a Show more control."
            )
        )
        layout.addWidget(back)

        options = QFormLayout()
        if not parts:
            self.furigana = QCheckBox("Show readings below example words")
            self.furigana.setChecked(settings.furigana)
            back_form.addRow("Furigana", self.furigana)
            self.word_status = QComboBox()
            self.word_status.addItem("All matching Anki words, including unreviewed cards", True)
            self.word_status.addItem("Only words with an Anki card I have reviewed", False)
            self.word_status.setCurrentIndex(self.word_status.findData(settings.include_new))
            self.word_status.setEnabled(False)
            self.word_status.setToolTip(
                "Not available yet. All matching Anki words are currently included. "
                "Chip colors on the back still show each word's saved review state."
            )
            options.addRow("Filter my Anki words by reviews", self.word_status)
        self.refresh = QCheckBox("Update examples on existing cards during Refresh")
        self.refresh.setChecked(settings.auto_refresh)
        self.refresh.setToolTip(
            "Uses the choices above during manual and automatic Refresh. "
            "Also requires Update example words in the Refresh tab."
        )
        options.addRow(self.refresh)
        layout.addLayout(options)
        layout.addWidget(
            _hint(
                "My Anki words means the Japanese text in the fields selected under Discovery. "
                "Other fields are not searched. Dictionary words come from the Jitendex selected "
                "under Dictionaries."
                if not parts
                else "Example kanji are characters containing this graphical part, "
                "rather than vocabulary words."
            )
        )
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
            selected = self.front_source.currentData()
            changes["front_example_source"] = (
                None
                if self.saved_settings.front_example_source is None
                and selected == changes["example_source"]
                else selected
            )
            changes["furigana"] = self.furigana.isChecked()
            changes["front_furigana"] = self.front_furigana.isChecked()
            changes["include_new"] = self.word_status.currentData()
        return replace(self.saved_settings, **changes)
