"""A single creation review with category tiles and an inline card preview."""

from dataclasses import replace

from aqt.operations import CollectionOp
from aqt.qt import (
    QColor,
    QComboBox,
    QDialog,
    QFont,
    QHBoxLayout,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSize,
    QSplitter,
    Qt,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from aqt.utils import showWarning, tooltip
from aqt.webview import AnkiWebView

from ..anki.generation import apply_generation
from ..anki.ignored import load_ignored, save_ignored
from ..generation.cards import CSS
from ..generation.review import category_for, exclude_ignored, render_card_preview


class CreationReviewDialog(QDialog):
    def __init__(self, mw, preview, *, summary_label="Refresh complete"):
        super().__init__(mw)
        self.mw, self.original = mw, preview
        self.summary_label = summary_label
        self.busy = False
        self.preview = preview
        self.ignored = load_ignored(mw.col)
        self.setObjectName("katanki_creation_review")
        self.setWindowTitle("Katanki — Create kanji cards")
        self.resize(980, 620)
        layout = QVBoxLayout(self)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        hint = QLabel(
            "Green cards will be created. Left-click to preview; right-click to ignore or enable."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        split = QSplitter()
        layout.addWidget(split, 1)
        self.tabs = QTabWidget()
        split.addWidget(self.tabs)
        self.tiles, self.decks = {}, {}
        contents = {content.identity: content for content in preview.contents}
        self.contents = contents
        self.options = {item.identity: item for item in preview.creations}
        self.items = {}
        candidates = [
            item
            for item in preview.plan.items
            if item.outcome == "create" and item.unit.identity not in self.ignored
        ]
        for category in ("recognition", "production", "parts"):
            category_items = [
                item for item in candidates if category_for(item.unit.identity) == category
            ]
            if not category_items:
                continue
            page = QWidget()
            column = QVBoxLayout(page)
            row = QHBoxLayout()
            row.addWidget(QLabel("Target deck"))
            deck = QComboBox()
            deck.addItem("Choose a target deck…", None)
            for entry in mw.col.decks.all_names_and_ids():
                deck.addItem(entry.name, entry.id)
            target = self.options[category_items[0].unit.identity].deck_id
            deck.setCurrentIndex(max(0, deck.findData(target)))
            self.decks[category] = deck
            deck.currentIndexChanged.connect(self._update)
            row.addWidget(deck, 1)
            column.addLayout(row)
            tiles = QListWidget()
            tiles.setAccessibleName(f"{category.title()} cards to create")
            tiles.setViewMode(QListView.ViewMode.IconMode)
            tiles.setResizeMode(QListView.ResizeMode.Adjust)
            tiles.setMovement(QListView.Movement.Static)
            tiles.setGridSize(QSize(88, 86))
            tiles.setSpacing(6)
            tiles.setWordWrap(True)
            tiles.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            tiles.itemClicked.connect(self._show_card)
            tiles.customContextMenuRequested.connect(
                lambda pos, view=tiles: self._right_click(view, pos)
            )
            for item in category_items:
                identity = item.unit.identity
                tile = QListWidgetItem(identity.key if len(identity.key) == 1 else item.unit.label)
                tile.setData(Qt.ItemDataRole.UserRole, identity)
                tile.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                tile.setFont(QFont("", 28 if len(identity.key) == 1 else 12))
                tile.setSizeHint(QSize(80, 78))
                tiles.addItem(tile)
                self.items[identity] = tile
            self.tiles[category] = tiles
            column.addWidget(tiles)
            self.tabs.addTab(page, category.title())
        side = QWidget()
        side_layout = QVBoxLayout(side)
        self.card_details = QLabel("Select a card to see its front and back.")
        self.card_details.setWordWrap(True)
        self.card_details.setTextFormat(Qt.TextFormat.PlainText)
        side_layout.addWidget(self.card_details)
        self.card_tabs = QTabWidget()
        self.front, self.back = AnkiWebView(parent=self), AnkiWebView(parent=self)
        self.card_tabs.addTab(self.front, "Front")
        self.card_tabs.addTab(self.back, "Back")
        side_layout.addWidget(self.card_tabs, 1)
        split.addWidget(side)
        split.setSizes([530, 450])
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        footer = QHBoxLayout()
        self.close_button = QPushButton("Cancel")
        self.close_button.clicked.connect(self.reject)
        footer.addWidget(self.close_button)
        footer.addStretch()
        self.create_button = QPushButton()
        self.create_button.setAutoDefault(False)
        self.create_button.clicked.connect(self._create)
        footer.addWidget(self.create_button)
        layout.addLayout(footer)
        self._update()
        self.finished.connect(self._cleanup)

    def _right_click(self, view, position):
        tile = view.itemAt(position)
        if tile is not None:
            self.toggle_ignored(tile.data(Qt.ItemDataRole.UserRole))

    def toggle_ignored(self, identity):
        if self.busy:
            return
        try:
            current = set(load_ignored(self.mw.col))
            if identity in current:
                current.remove(identity)
            else:
                current.add(identity)
            save_ignored(self.mw.col, current)
            self.ignored = frozenset(current)
        except Exception as error:
            showWarning(f"Could not save ignored cards: {error}", parent=self)
            return
        self._update()

    def _update(self, *_):
        if not hasattr(self, "create_button"):
            return
        self.preview = exclude_ignored(self.original, self.ignored)
        outcomes = {item.unit.identity: item for item in self.preview.plan.items}
        for identity, tile in self.items.items():
            item = outcomes[identity]
            ignored = identity in self.ignored
            enabled = item.outcome == "create"
            tile.setBackground(
                QColor("#286442" if enabled else "#454b55" if ignored else "#6a532a")
            )
            tile.setForeground(QColor("#ffffff"))
            tile.setToolTip(
                f"{identity.key} · {identity.note_type}\n"
                + (
                    "Will be created. Left-click to preview; right-click to ignore."
                    if enabled
                    else "Ignored (saved). Right-click to enable."
                    if ignored
                    else item.reason
                )
            )
        creating = [item for item in self.preview.plan.items if item.outcome == "create"]
        existing = sum(item.outcome == "skip" for item in self.preview.plan.items)
        blocked = [
            item
            for item in self.preview.plan.items
            if item.outcome == "unavailable" and item.unit.identity not in self.ignored
        ]
        self.summary.setText(
            f"{self.summary_label} · {existing:,} already present · {len(creating):,} new cards"
        )
        details = [f"{item.unit.identity.key}: {item.reason}" for item in blocked]
        self.status.setText(
            f"{len(self.ignored):,} saved ignores · {len(blocked):,} unavailable. "
            "Ignore choices are saved immediately, including when you cancel."
        )
        self.status.setToolTip("\n".join((*details, *self.preview.warnings)))
        targets_ready = all(
            self.decks[category_for(item.unit.identity)].currentData() is not None
            for item in creating
        )
        self.create_button.setText(f"Create {len(creating):,} cards")
        self.create_button.setEnabled(bool(creating) and targets_ready and not self.busy)
        self.create_button.setToolTip(
            "" if targets_ready else "Choose a target deck in each category."
        )

    def _show_card(self, tile):
        identity = tile.data(Qt.ItemDataRole.UserRole)
        content = self.contents.get(identity)
        if content is None:
            self.card_details.setText("A card preview is unavailable for this item.")
            return
        front, back = render_card_preview(content)
        for web, html in ((self.front, front), (self.back, back)):
            web.stdHtml(f'<style>{CSS}</style><div class="card">{html}</div>')
        category = category_for(identity)
        tags = self.options[identity].tags
        self.card_details.setText(
            f"{identity.key} · {category.title()}\nDeck: {self.decks[category].currentText()}\n"
            f"Tags: {', '.join(tags) or 'none'}"
        )

    def _create(self):
        if self.busy or not self.create_button.isEnabled():
            return
        # Freeze precisely the visible enabled cards, decks, tags, and prerequisite decisions.
        preview = exclude_ignored(self.original, self.ignored | load_ignored(self.mw.col))
        options = tuple(
            replace(item, deck_id=self.decks[category_for(item.identity)].currentData())
            for item in preview.creations
        )
        preview = replace(preview, creations=options)
        self.busy = True
        self.tabs.setEnabled(False)
        self.close_button.setEnabled(False)
        self.create_button.setEnabled(False)
        try:
            CollectionOp(
                parent=self.mw, op=lambda collection: apply_generation(collection, preview)
            ).success(self._applied).failure(self._failed).run_in_background()
        except Exception as error:
            self._failed(error)

    def _applied(self, result):
        self.busy = False
        tooltip(
            f"Created {result.created} cards. {result.skipped} newly existing cards skipped.",
            parent=self.mw,
        )
        self.accept()

    def _failed(self, error):
        self.busy = False
        self.tabs.setEnabled(True)
        self.close_button.setEnabled(True)
        self._update()
        showWarning(str(error), parent=self)

    def _cleanup(self, *_):
        self.front.cleanup()
        self.back.cleanup()

    def reject(self):
        if not self.busy:
            super().reject()
