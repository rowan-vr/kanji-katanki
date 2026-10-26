"""Source mappings and explicit review for card-ID-preserving migration."""

from collections import Counter
from time import monotonic

from aqt.operations import CollectionOp, QueryOp
from aqt.qt import (
    QComboBox,
    QDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTimer,
    QVBoxLayout,
    QWidget,
)
from aqt.utils import showInfo, showWarning

from ..anki.identities import MODEL_MARKER
from ..anki.migration import CATEGORIES, MigrationSource, apply_migration, prepare_migration


class MigrationMapping(QGroupBox):
    def __init__(self, collection, category):
        super().__init__("Recognition" if category == "recognition" else "Production / writing")
        self.category = category
        self.models = {
            m["id"]: m
            for m in collection.models.all()
            if not m.get(MODEL_MARKER) and m.get("type") == 0
        }
        layout = QGridLayout(self)
        self.deck, self.model, self.field = (QComboBox() for _ in range(3))
        self.deck.addItem("Skip this category", None)
        for deck in collection.decks.all_names_and_ids():
            self.deck.addItem(deck.name, deck.id)
        self.model.addItem("Choose a note type…", None)
        for model in sorted(self.models.values(), key=lambda m: m["name"]):
            self.model.addItem(model["name"], model["id"])
        for row, (label, combo) in enumerate(
            (
                ("1. Source deck", self.deck),
                ("2. Note type", self.model),
                ("3. Character field", self.field),
            )
        ):
            combo.setAccessibleName(f"{category} {label}")
            combo.setMinimumContentsLength(17)
            combo.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
            )
            layout.addWidget(QLabel(label), row, 0)
            layout.addWidget(combo, row, 1)
        self.deck.setToolTip(
            "Only cards in this exact deck are selected; choose child decks separately."
        )
        self.field.setToolTip("The field containing a single kanji or radical character.")
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status, 3, 0, 1, 2)
        self.deck.currentIndexChanged.connect(self._update)
        self.model.currentIndexChanged.connect(self._model_changed)
        self.field.currentIndexChanged.connect(self._update)
        self._model_changed()

    def _model_changed(self):
        self.field.clear()
        self.field.addItem("Choose the character field…", None)
        model = self.models.get(self.model.currentData())
        if model:
            for field in model["flds"]:
                self.field.addItem(field["name"], field["name"])
            fields = [
                i
                for i in range(1, self.field.count())
                if self.field.itemText(i).casefold() in ("character", "kanji", "字")
            ]
            if len(fields) == 1:
                self.field.setCurrentIndex(fields[0])
            elif len(model["flds"]) == 1:
                self.field.setCurrentIndex(1)
        self._update()

    def active(self):
        return self.deck.currentData() is not None

    def complete(self):
        return self.active() and all(
            combo.currentData() is not None for combo in (self.model, self.field)
        )

    def _update(self, *_):
        self.model.setEnabled(self.active())
        ready = self.active() and self.model.currentData() is not None
        self.field.setEnabled(ready)
        if not self.active():
            text = "Optional — choose a source deck to include these cards."
        elif self.complete():
            text = "Ready to preview. Kanji and parts are identified from the character."
        else:
            missing = next(
                label
                for label, combo in (
                    ("note type", self.model),
                    ("character field", self.field),
                )
                if combo.currentData() is None
            )
            text = f"Choose a {missing} to continue."
        self.status.setText(text)

    def source(self):
        if not self.complete():
            raise ValueError("Complete the source deck, note type and character field.")
        return MigrationSource(
            self.category,
            self.deck.currentData(),
            self.model.currentData(),
            self.field.currentData(),
        )


class MigrationDialog(QDialog):
    def __init__(self, mw):
        super().__init__(mw)
        self.mw, self.collection = mw, mw.col
        self.busy, self.plan = False, None
        self._last_progress = 0.0
        self._progress_state = ("Preparing migration…", 0, 0)
        self.setWindowTitle("Katanki — Migrate Existing Cards")
        self.resize(830, 640)
        layout = QVBoxLayout(self)
        hint = QLabel(
            "Choose the cards you already study, then review their Katanki destinations. "
            "Card IDs, scheduling and review history are preserved."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.mappings = {}
        self.sources = QWidget()
        sources_layout = QHBoxLayout(self.sources)
        sources_layout.setContentsMargins(0, 0, 0, 0)
        for category in CATEGORIES:
            mapping = MigrationMapping(mw.col, category)
            self.mappings[category] = mapping
            sources_layout.addWidget(mapping)
        layout.addWidget(self.sources)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.review = QTableWidget(0, 6)
        self.review.setHorizontalHeaderLabels(
            ["Character", "Convert to", "Interval (days)", "Reviews", "Lapses", "History entries"]
        )
        self.review.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.review.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.review.setAccessibleName("Cards to migrate")
        layout.addWidget(self.review, 1)
        self.warnings = QPlainTextEdit()
        self.warnings.setReadOnly(True)
        self.warnings.setPlaceholderText(
            "Skipped cards and warnings will appear here after preview."
        )
        self.warnings.setMaximumHeight(95)
        self.warnings.hide()
        self.warnings.setAccessibleName("Migration warnings and skipped cards")
        layout.addWidget(self.warnings)
        footer = QLabel(
            "A backup is made before conversion. Decks and tags stay unchanged. "
            "Note IDs may change. You can undo the conversion."
        )
        footer.setWordWrap(True)
        layout.addWidget(footer)
        row = QHBoxLayout()
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.reject)
        self.preview_button = QPushButton("Preview cards →")
        self.preview_button.clicked.connect(self.preview)
        self.preview_button.setDefault(True)
        self.apply_button = QPushButton("Convert reviewed cards")
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self.apply)
        for button in (self.close_button, self.preview_button, self.apply_button):
            row.addWidget(button)
        layout.addLayout(row)
        for mapping in self.mappings.values():
            for combo in (mapping.deck, mapping.model, mapping.field):
                combo.currentIndexChanged.connect(self.invalidate)
        self.invalidate()

    def invalidate(self, *_):
        self.plan = None
        self.apply_button.setEnabled(False)
        self.review.setRowCount(0)
        self.warnings.clear()
        self.warnings.hide()
        self._update_controls()

    def _busy(self, busy):
        self.busy = busy
        self.sources.setEnabled(not busy)
        if busy:
            self._last_progress = 0.0
            self._progress_state = ("Preparing migration…", 0, 0)
        self._update_controls()

    def _progress(self, message, current=0, total=0):
        # Rate-limit queued events; only the main thread touches Anki's popup.
        now = monotonic()
        content_update = message.startswith("Preparing ") and ": " in message
        if (current or content_update) and not (total and current == total):
            if now - self._last_progress < 0.1:
                return
        self._last_progress = now
        label = f"{message} ({current:,} of {total:,})" if total else message

        def update():
            if self.busy:
                self._progress_state = (label, current, total)
                self.mw.progress.update(label=label, value=current, max=total)

        self.mw.taskman.run_on_main(update)

    def _popup_progress(self, _backend_progress, update):
        # Refresh even while a long dictionary load/backup emits no new events.
        # Anki's popup may appear after the first stage callback has already run.
        update.label, update.value, update.max = self._progress_state

    def _update_controls(self):
        active = [m for m in self.mappings.values() if m.active()]
        complete = bool(active) and all(m.complete() for m in active)
        self.preview_button.setEnabled(not self.busy and complete)
        self.close_button.setEnabled(not self.busy)
        self.apply_button.setEnabled(not self.busy and bool(self.plan and self.plan.items))
        self.apply_button.setText(
            f"Convert {len(self.plan.items)} {'card' if len(self.plan.items) == 1 else 'cards'}"
            if self.plan and self.plan.items
            else "Convert reviewed cards"
        )
        if self.busy:
            self.summary.setText("Preparing migration…")
        elif self.plan:
            counts = Counter(
                (i.identity.kind, i.identity.note_type.rsplit("-", 1)[1]) for i in self.plan.items
            )
            breakdown = ", ".join(
                f"{amount} {'parts' if kind == 'primitive' else 'kanji'} {mode}"
                for (kind, mode), amount in sorted(counts.items())
            )
            self.summary.setText(
                f"Ready to convert {len(self.plan.items)} "
                f"{'card' if len(self.plan.items) == 1 else 'cards'}: {breakdown}. "
                "Review the destinations below before converting."
                if self.plan.items
                else "No cards can be converted. See the skipped-card details below."
            )
        elif not active:
            self.summary.setText(
                "Choose a source deck for Recognition or Production to get started."
            )
        elif not complete:
            self.summary.setText("Finish the source choices above to preview your cards.")
        else:
            self.summary.setText("Sources ready. Preview cards to check their destinations.")

    def preview(self):
        if self.busy or not self.preview_button.isEnabled():
            return
        try:
            sources = tuple(m.source() for m in self.mappings.values() if m.active())
        except ValueError as error:
            showWarning(str(error), parent=self)
            return
        self.invalidate()
        self._busy(True)
        QueryOp(
            parent=self.mw,
            op=lambda col: prepare_migration(col, sources, progress=self._progress),
            success=self.loaded,
        ).failure(self.failed).with_backend_progress(self._popup_progress).run_in_background()

    def loaded(self, plan):
        from anki.cards_pb2 import Card

        if self.mw.col is not self.collection:
            self.failed(ValueError("Profile changed; reopen migration."))
            return
        self.plan = plan
        self.review.setRowCount(len(plan.items))
        for row, item in enumerate(plan.items):
            card = Card.FromString(item.card_snapshot)
            kind = "Part" if item.identity.kind == "primitive" else "Kanji"
            mode = "recognition" if item.identity.note_type.endswith("recognition") else "writing"
            for column, value in enumerate(
                (
                    item.identity.key,
                    f"{kind} · {mode}",
                    card.interval,
                    card.reps,
                    card.lapses,
                    len(item.history_snapshot),
                )
            ):
                cell = QTableWidgetItem(str(value))
                cell.setToolTip(f"Original card ID: {item.card_id}")
                self.review.setItem(row, column, cell)
        self.warnings.setPlainText("\n".join(plan.warnings))
        self.warnings.setVisible(bool(plan.warnings))
        self._busy(False)

    def apply(self):
        if self.busy or not self.plan or not self.plan.items:
            return
        plan = self.plan
        self._busy(True)
        self.summary.setText("Backing up and converting cards…")
        backup_folder = self.mw.pm.backupFolder()

        def convert(col):
            if col is not self.collection:
                raise ValueError("Profile changed; reopen migration.")
            self._progress("Creating collection backup…")
            col.create_backup(backup_folder=backup_folder, force=True, wait_for_completion=True)
            return apply_migration(col, plan, progress=self._progress)

        def complete(_):
            self.plan = None
            self._busy(False)
            self.summary.setText(
                f"Converted {len(plan.items)} cards. Anki Undo can revert migration."
            )
            showInfo(
                f"Converted {len(plan.items)} cards. Their card IDs, scheduling and review "
                "history were preserved. These are the original cards, so no old-card cleanup "
                "is needed. Use Anki Undo to revert migration.",
                parent=self,
            )
            self.accept()
            QTimer.singleShot(0, self._refresh_after_migration)

        CollectionOp(parent=self.mw, op=convert).success(complete).failure(
            self.failed
        ).with_backend_progress(self._popup_progress).run_in_background()

    def _refresh_after_migration(self):
        if self.mw.col is self.collection:
            from .refresh import open_refresh

            open_refresh(self.mw)

    def failed(self, error):
        self.plan = None
        self._busy(False)
        showWarning(f"Migration could not complete:\n{error}", parent=self)

    def reject(self):
        if not self.busy:
            super().reject()

    def closeEvent(self, event):
        if self.busy:
            event.ignore()
        else:
            super().closeEvent(event)


def open_migration(mw):
    dialog = MigrationDialog(mw)
    dialog.exec()
