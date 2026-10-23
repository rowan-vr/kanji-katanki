"""Editable source rules shared by Discovery settings and one-off scans."""

from aqt.qt import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from ..anki.collection import resolve_sources, scan_sources
from ..config import SourceRule


class FieldSelector(QPushButton):
    """Compact field summary with a checkbox popup for multiple choices."""

    def __init__(self):
        super().__init__("Select fields…")
        self.setAccessibleName("Source fields (multiple selection)")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.menu = QMenu(self)
        self.setMenu(self.menu)
        self.checkboxes = []

    def set_fields(self, fields, selected=()):
        self.menu.clear()
        self.checkboxes = []
        for name in dict.fromkeys((*fields, *selected)):
            check = QCheckBox(name)
            check.setContentsMargins(10, 5, 16, 5)
            check.setChecked(name in selected)
            action = QWidgetAction(self.menu)
            action.setDefaultWidget(check)
            self.menu.addAction(action)
            check.toggled.connect(self._update_summary)
            self.checkboxes.append(check)
        self._update_summary()

    def selected_fields(self):
        return tuple(check.text() for check in self.checkboxes if check.isChecked())

    def _update_summary(self):
        selected = self.selected_fields()
        self.setText(
            selected[0]
            if len(selected) == 1
            else f"{len(selected)} fields selected"
            if selected
            else "Select fields…"
        )
        self.setToolTip(", ".join(selected) or "Choose one or more vocabulary fields")


class SourceRow(QFrame):
    def __init__(self, mw, remove, rule=None):
        super().__init__(mw)
        decks, self.note_types = scan_sources(mw.col)
        self.deck_names = dict(decks)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        layout = QGridLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(6)
        for column, title in enumerate(("Deck or pattern", "Note type", "Fields")):
            layout.addWidget(QLabel(title), 0, column)
            layout.setColumnStretch(column, 1)
        self.deck = QComboBox()
        self.deck.setEditable(True)
        self.deck.setAccessibleName("Source deck or wildcard pattern")
        self.deck.addItem("*", None)
        for deck_id, name in decks:
            self.deck.addItem(name, deck_id)
        self.deck.setMinimumWidth(0)
        self.deck.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        layout.addWidget(self.deck, 1, 0)
        self.types = QComboBox()
        self.types.setAccessibleName("Source note type")
        for model_id, name, _ in self.note_types:
            self.types.addItem(name, model_id)
        self.types.setMinimumWidth(0)
        self.types.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        layout.addWidget(self.types, 1, 1)
        self.fields = FieldSelector()
        layout.addWidget(self.fields, 1, 2)
        button = QPushButton("Remove")
        button.setToolTip("Remove this vocabulary source")
        button.clicked.connect(lambda: remove(self))
        layout.addWidget(button, 1, 3)
        self.types.currentIndexChanged.connect(self._fields_changed)
        self._fields_changed()
        if rule is not None:
            if rule.deck_ids:
                deck_id = rule.deck_ids[0]
                index = self.deck.findData(deck_id)
                if index < 0:
                    self.deck.addItem(f"Missing deck ({deck_id})", deck_id)
                    index = self.deck.count() - 1
                self.deck.setCurrentIndex(index)
            else:
                self.deck.setCurrentIndex(0)
                self.deck.setEditText(rule.deck_pattern)
            index = self.types.findData(rule.note_type_id)
            if index < 0:
                self.types.addItem(f"Missing note type ({rule.note_type_id})", rule.note_type_id)
                index = self.types.count() - 1
            self.types.setCurrentIndex(index)
            fields = next(
                (entry[2] for entry in self.note_types if entry[0] == rule.note_type_id), ()
            )
            self.fields.set_fields(fields, rule.fields)

    def _fields_changed(self, index=0):
        fields = next(
            (entry[2] for entry in self.note_types if entry[0] == self.types.currentData()), ()
        )
        self.fields.set_fields(fields)

    def rule(self):
        model_id = self.types.currentData()
        fields = self.fields.selected_fields()
        known = next((entry[2] for entry in self.note_types if entry[0] == model_id), None)
        if known is None or not set(fields) <= set(known):
            raise ValueError("A source note type or field is missing. Choose its replacement.")
        # Preserve IDs for catalog choices. Typed text is a name/pattern, never a query.
        deck_id = self.deck.currentData()
        text = self.deck.currentText().strip()
        if deck_id is not None and text == self.deck.itemText(self.deck.currentIndex()):
            if deck_id not in self.deck_names:
                raise ValueError("A source deck is missing. Choose its replacement.")
            return SourceRule("", model_id, fields, (deck_id,))
        return SourceRule(text, model_id, fields)


class SourceSelector(QWidget):
    def __init__(self, mw):
        super().__init__(mw)
        self.mw = mw
        self.rows = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        self.rules_layout = QVBoxLayout(container)
        self.rules_layout.setContentsMargins(0, 0, 0, 0)
        self.rules_layout.setSpacing(10)
        self.rules_layout.addStretch()
        scroll.setWidget(container)
        scroll.setMinimumHeight(170)
        layout.addWidget(scroll)
        add = QPushButton("Add source")
        add.clicked.connect(lambda: self.add_rule())
        footer = QHBoxLayout()
        footer.addWidget(add)
        footer.addStretch()
        layout.addLayout(footer)
        self.add_rule()

    def add_rule(self, rule=None):
        row = SourceRow(self.mw, self.remove_rule, rule)
        self.rows.append(row)
        self.rules_layout.insertWidget(self.rules_layout.count() - 1, row)
        return row

    def remove_rule(self, row):
        self.rows.remove(row)
        self.rules_layout.removeWidget(row)
        row.setParent(None)
        row.deleteLater()

    def restore(self, rules):
        for row in list(self.rows):
            self.remove_rule(row)
        for rule in rules:
            # Version 1 allowed several explicit decks in one source.
            if rule.deck_ids:
                for deck_id in rule.deck_ids:
                    self.add_rule(SourceRule("", rule.note_type_id, rule.fields, (deck_id,)))
            else:
                self.add_rule(rule)
        if not self.rows:
            self.add_rule()

    def rules(self):
        if not self.rows:
            raise ValueError("Add at least one vocabulary source.")
        rules = []
        for index, row in enumerate(self.rows, 1):
            try:
                rules.append(row.rule())
            except ValueError as error:
                row.setFocus()
                raise ValueError(f"Source {index}: {error}") from error
        return tuple(rules)

    def selection(self):
        return resolve_sources(self.mw.col, self.rules())
