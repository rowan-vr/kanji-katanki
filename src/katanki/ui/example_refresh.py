"""Explicit before/after review for legacy notes without generated-value baselines."""

from aqt.qt import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QGroupBox,
    QLabel,
    QListWidget,
    QScrollArea,
    QSplitter,
    Qt,
    QVBoxLayout,
    QWidget,
)

from ..generation.examples import STATE_FIELD, lines

FIELD_LABELS = {
    "VocabExamples": "Example words",
    "ExampleLimit": "Examples shown",
    "Attribution": "Credits",
    "Prompt": "Production clue",
    "Meanings": "Meanings",
    "Readings": "Readings",
    "Components": "Components",
    "Strokes": "Stroke diagram",
}
CARD_LABELS = {
    "kanji-recognition": "Recognition",
    "kanji-production": "Production",
    "primitive-recognition": "Part recognition",
    "primitive-production": "Part production",
}


def _label(text):
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


def _display_value(field, value):
    if not value.strip():
        return "None"
    if field == "ExampleLimit":
        return {"0": "All examples", "-1": "Hidden"}.get(value, f"Up to {value} examples")
    if field == "Strokes":
        return "Stroke diagram present"
    return "\n".join(lines(value)) or "None"


def review_migration(mw, updates):
    updates = tuple(updates)
    dialog = QDialog(mw)
    dialog.setWindowTitle("Katanki — Review example replacements")
    dialog.resize(1000, 680)
    layout = QVBoxLayout(dialog)
    heading = _label(f"Review replacements on {len(updates):,} existing cards")
    font = heading.font()
    font.setBold(True)
    font.setPointSize(font.pointSize() + 2)
    heading.setFont(font)
    layout.addWidget(heading)
    layout.addWidget(
        _label(
            "These cards were created before change tracking was added. Compare the current "
            "and proposed values before allowing future example refreshes. Your own examples, "
            "review progress, tags and decks are kept. Cancel keeps these cards unchanged."
        )
    )
    split = QSplitter()
    cards = QListWidget()
    cards.setMinimumWidth(190)
    for update in updates:
        category = CARD_LABELS.get(update.identity.note_type, update.identity.note_type)
        cards.addItem(f"{update.identity.key}  ·  {category}")
        cards.item(cards.count() - 1).setToolTip(f"Note {update.note_id}")
    split.addWidget(cards)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    split.addWidget(scroll)
    split.setStretchFactor(1, 1)
    split.setSizes([230, 730])
    layout.addWidget(split, 1)

    def show_changes(index):
        if index < 0:
            return
        update = updates[index]
        panel = QWidget()
        changes = QVBoxLayout(panel)
        before = dict(update.before)
        for field, value in update.after:
            previous = before.get(field, "")
            if field == STATE_FIELD or previous == value:
                continue
            group = QGroupBox(FIELD_LABELS.get(field, field))
            grid = QGridLayout(group)
            grid.setColumnStretch(0, 1)
            grid.setColumnStretch(1, 1)
            for column, (title, content) in enumerate(
                (("Current", previous), ("After refresh", value))
            ):
                title_label = _label(title)
                title_font = title_label.font()
                title_font.setBold(True)
                title_label.setFont(title_font)
                grid.addWidget(title_label, 0, column)
                text = _label(_display_value(field, content))
                text.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
                grid.addWidget(text, 1, column)
            changes.addWidget(group)
        changes.addStretch()
        old = scroll.takeWidget()
        if old is not None:
            old.deleteLater()
        scroll.setWidget(panel)
        scroll.verticalScrollBar().setValue(0)

    cards.currentRowChanged.connect(show_changes)
    cards.setCurrentRow(0)
    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Approve replacements")
    buttons.button(QDialogButtonBox.StandardButton.Cancel).setDefault(True)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    return dialog.exec() == QDialog.DialogCode.Accepted
