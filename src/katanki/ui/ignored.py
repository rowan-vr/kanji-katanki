"""Inspect and restore persistently ignored card types and characters."""

from aqt.qt import (
    QAbstractItemView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    Qt,
    QVBoxLayout,
    QWidget,
)
from aqt.utils import showWarning

from ..anki.ignored import load_ignored, save_ignored
from ..generation.review import category_for


class IgnoredCardsPanel(QWidget):
    def __init__(self, mw):
        super().__init__()
        self.mw = mw
        layout = QVBoxLayout(self)
        hint = QLabel(
            "Ignored cards are skipped on refresh. Restore a card to make it eligible next time. "
            "Changes here are saved immediately; existing cards are never deleted."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.cards = QListWidget()
        self.cards.setAccessibleName("Ignored cards")
        self.cards.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        layout.addWidget(self.cards)
        self.restore_button = QPushButton("Restore selected cards")
        self.restore_button.clicked.connect(self._restore)
        self.cards.itemSelectionChanged.connect(
            lambda: self.restore_button.setEnabled(bool(self.cards.selectedItems()))
        )
        layout.addWidget(self.restore_button)
        self.reload()

    def reload(self):
        self.cards.clear()
        for identity in sorted(load_ignored(self.mw.col)):
            item = QListWidgetItem(
                f"{identity.key} — {category_for(identity).title()} ({identity.note_type})"
            )
            item.setData(Qt.ItemDataRole.UserRole, identity)
            self.cards.addItem(item)
        self.restore_button.setEnabled(False)

    def _restore(self):
        try:
            selected = {item.data(Qt.ItemDataRole.UserRole) for item in self.cards.selectedItems()}
            save_ignored(self.mw.col, load_ignored(self.mw.col) - selected)
            self.reload()
        except Exception as error:
            showWarning(f"Could not restore ignored cards: {error}", parent=self)
