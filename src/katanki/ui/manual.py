"""Explicit kanji entry using the configured generation and creation review."""

from aqt.operations import QueryOp
from aqt.qt import (
    QCheckBox,
    QComboBox,
    QCompleter,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    Qt,
    QTimer,
    QVBoxLayout,
)
from aqt.utils import showWarning

from ..anki.refresh import prepare_targets
from ..anki.target_lists import store_for_collection
from ..config import load_settings
from ..generation.discovery import extract_candidates
from ..stats.groups import coverage_sections
from ..stats.sources import load_target_registry
from .generation import CreationReviewDialog


class ManualKanjiDialog(QDialog):
    def __init__(self, mw, *, targets=None, source_title=""):
        super().__init__(mw)
        self.mw = mw
        self.targets = tuple(targets) if targets is not None else None
        self.busy = False
        self._list_signature = None
        self._list_result = None
        self._list_pending = False
        self._list_error = ""
        self._manual_text = ""
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(200)
        self._preview_timer.timeout.connect(self._prepare_list)
        self.setWindowTitle("Katanki — New Kanji Cards")
        self.resize(520, 440)
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)
        hint = QLabel(
            "Choose a list or enter kanji manually, then review the cards before adding them."
        )
        hint.setWordWrap(True)
        hint.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        layout.addWidget(hint)
        self.source = QComboBox()
        self.source.setAccessibleName("Kanji source")
        self.source.setMaximumWidth(380)
        self.source.setMaxVisibleItems(16)
        self.source.setToolTip("Type to search lists and groups, or choose Manual input.")
        self.source.setMinimumContentsLength(24)
        self.source.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.source.setEditable(True)
        self.source.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.source.addItem("Manual input", None)
        try:
            registry = load_target_registry(choices=load_settings(mw.col).dictionaries)
            if getattr(mw.col, "path", None):
                for target in store_for_collection(mw.col).load():
                    registry.register(target)
            sections = coverage_sections(registry)
            titles = {section.key: section.title for section in sections}
            for section in sections:
                title = section.title
                if section.parent:
                    title = f"{titles[section.parent]} › {title}"
                self.source.addItem(title, section.characters)
            completer = self.source.completer()
            completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
            completer.setFilterMode(Qt.MatchFlag.MatchContains)
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            self.source.lineEdit().setPlaceholderText("Search lists or groups…")
        except (OSError, ValueError) as error:
            showWarning(f"Could not load target lists:\n{error}", parent=self)
        source_row = QHBoxLayout()
        source_row.addWidget(QLabel("Source"))
        source_row.addWidget(self.source, 1)
        source_row.addStretch()
        layout.addLayout(source_row)
        amount_row = QHBoxLayout()
        amount_row.addWidget(QLabel("Kanji to add"))
        self.amount = QSpinBox()
        self.amount.setRange(1, 100000)
        self.amount.setMaximumWidth(100)
        self.amount.setValue(10)
        self.amount.setAccessibleName("Number of kanji to add")
        amount_row.addWidget(self.amount)
        self.all_targets = QCheckBox("All")
        amount_row.addWidget(self.all_targets)
        amount_row.addStretch()
        layout.addLayout(amount_row)
        amount_hint = QLabel(
            "Existing cards and saved ignores are skipped. The amount counts kanji; "
            "selected card types and required parts may create multiple cards."
        )
        amount_hint.setWordWrap(True)
        layout.addWidget(amount_hint)
        self.text = QPlainTextEdit()
        self.text.setAccessibleName("Kanji to add")
        self.text.setMinimumHeight(90)
        self.text.setPlaceholderText("日本語…")
        layout.addWidget(self.text)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        selection = QHBoxLayout()
        self.type_buttons = {}
        for category in ("recognition", "production", "parts"):
            button = QCheckBox(category.title())
            button.setChecked(category != "parts")
            button.setToolTip(f"Include {category} cards for the entered kanji")
            button.toggled.connect(self._update)
            self.type_buttons[category] = button
            selection.addWidget(button)
        layout.addLayout(selection)
        row = QHBoxLayout()
        self.cancel = QPushButton("Cancel")
        self.cancel.clicked.connect(self.reject)
        row.addWidget(self.cancel)
        row.addStretch()
        self.create_button = QPushButton("Create")
        self.create_button.clicked.connect(self._preview)
        row.addWidget(self.create_button)
        layout.addLayout(row)
        if self.targets is not None:
            self.setWindowTitle("Katanki — Create Cards from Lists")
            hint.setText(
                f"Selected: {source_title}\n"
                "Review the selected list targets below and choose card types. "
                "Search and state filters do not change this selection. "
                "Existing cards and saved ignores are checked before the final creation review."
            )
            self.text.setPlainText("".join(self.targets))
            self.text.setReadOnly(True)
            self.create_button.setText("Review cards…")
        hint.setMinimumHeight(hint.heightForWidth(440))
        amount_hint.setMinimumHeight(amount_hint.heightForWidth(440))
        self.source.currentIndexChanged.connect(self._source_changed)
        self.all_targets.toggled.connect(self._update)
        self.amount.valueChanged.connect(self._update)
        self.text.textChanged.connect(self._update)
        self._update()

    def _source_changed(self, *_):
        if self.targets is None:
            self._manual_text = self.text.toPlainText()
        self.targets = self.source.currentData()
        self.text.setReadOnly(self.targets is not None)
        if self.targets is None:
            self.text.setPlainText(self._manual_text)
        self._update()

    def _categories(self):
        return tuple(kind for kind, button in self.type_buttons.items() if button.isChecked())

    def _set_text(self, value, *, empty=False):
        self.text.blockSignals(True)
        self.text.setPlainText(value)
        self.text.setStyleSheet("QPlainTextEdit { color: #d32f2f; }" if empty else "")
        self.text.blockSignals(False)

    def _update(self, *_):
        list_mode = self.targets is not None
        self.source.setEnabled(not self.busy)
        self.amount.setEnabled(list_mode and not self.busy and not self.all_targets.isChecked())
        self.all_targets.setEnabled(list_mode and not self.busy)
        categories = self._categories()
        for button in self.type_buttons.values():
            button.setEnabled(not self.busy)
        if list_mode:
            signature = (
                self.targets,
                categories,
                None if self.all_targets.isChecked() else self.amount.value(),
            )
            if signature != self._list_signature:
                self._list_signature = signature
                self._list_result = None
                self._list_error = ""
                self._list_pending = bool(categories)
                self._set_text("Checking for new cards…" if categories else "")
                self._preview_timer.start()
            ready = self._list_result is not None and self._has_creations(self._list_result)
            self.create_button.setEnabled(ready and bool(categories) and not self.busy)
            if self._list_pending:
                self.status.setText("Checking existing cards and preparing the selected amount…")
            elif self._list_error:
                self.status.setText(self._list_error)
            elif not categories:
                self.status.setText("Select at least one card type.")
        else:
            self._preview_timer.stop()
            self._list_signature = None
            self._list_result = None
            self._list_pending = False
            self.text.setStyleSheet("")
            count = len(extract_candidates(self.text.toPlainText()))
            self.create_button.setEnabled(bool(count) and bool(categories) and not self.busy)
            self.status.setText(
                f"{count:,} unique kanji" if categories else "Select at least one card type."
            )

    @staticmethod
    def _has_creations(result):
        return result.preview is not None and any(
            item.outcome == "create" for item in result.preview.plan.items
        )

    def _prepare_list(self):
        signature = self._list_signature
        if signature is None or not signature[1]:
            return
        targets, categories, limit = signature
        try:
            settings = load_settings(self.mw.col)
            QueryOp(
                parent=self.mw,
                op=lambda collection: prepare_targets(
                    collection, settings, targets, categories=categories, limit=limit
                ),
                success=lambda result: self._list_finished(signature, result),
            ).failure(lambda error: self._list_failed(signature, error)).run_in_background()
        except Exception as error:
            self._list_failed(signature, error)

    def _list_finished(self, signature, result):
        if signature != self._list_signature:
            return
        self._list_pending = False
        self._list_result = result
        items = result.preview.plan.items if result.preview else ()
        identities = {item.unit.identity for item in items if item.outcome == "create"}
        characters = {identity.key for identity in identities if identity.kind == "kanji"}
        if signature[1] == ("parts",):
            parts = {identity.key for identity in identities}
            characters = {
                visual.character
                for visual in result.report.strokes
                if any(component.key in parts for component in visual.component_entries)
            }
        targets = tuple(character for character in signature[0] if character in characters)
        empty = not self._has_creations(result)
        self._set_text("No new cards" if empty else "".join(targets), empty=empty)
        self.status.setText(
            "No new cards to add." if empty else f"{len(targets):,} kanji ready to add"
        )
        self._update()

    def _list_failed(self, signature, error):
        if signature != self._list_signature:
            return
        self._list_pending = False
        self._list_error = f"Could not check new cards: {error}"
        self._set_text("")
        self._update()

    def _set_busy(self, busy):
        self.busy = busy
        self.text.setEnabled(not busy)
        self.cancel.setEnabled(not busy)
        self._update()
        if busy:
            self.status.setText("Preparing kanji cards…")

    def _preview(self):
        if self.busy or not self.create_button.isEnabled():
            return
        if self.targets is not None:
            if self._list_result is not None:
                self._finished(self._list_result)
            return
        try:
            settings = load_settings(self.mw.col)
            text = self.text.toPlainText()
            prepare = prepare_targets
            candidates = (
                self.targets
                if self.targets is not None
                else tuple(sorted(extract_candidates(text)))
            )
            limit = None
            categories = tuple(
                kind for kind, button in self.type_buttons.items() if button.isChecked()
            )
            self._set_busy(True)
            QueryOp(
                parent=self.mw,
                op=lambda collection: prepare(
                    collection,
                    settings,
                    candidates,
                    categories=categories,
                    progress=self._progress,
                    limit=limit,
                ),
                success=self._finished,
            ).failure(self._failed).with_progress(
                "Katanki: preparing kanji cards"
            ).run_in_background()
        except Exception as error:
            self._failed(error)

    def _progress(self, message):
        # Background operations must queue all widget updates on Anki's main thread.
        def update():
            if self.busy:
                self.status.setText(message)
                self.mw.progress.update(label=message)

        self.mw.taskman.run_on_main(update)

    def _finished(self, result):
        self._set_busy(False)
        if not result.report.dictionary_loaded:
            showWarning("Enable KANJIDIC2 in Katanki → Settings → Dictionaries.", parent=self)
        elif result.preview is not None and any(
            item.outcome == "create" for item in result.preview.plan.items
        ):
            review = CreationReviewDialog(self.mw, result.preview, summary_label="Kanji ready")
            if review.exec():
                self.accept()
        else:
            items = result.preview.plan.items if result.preview else ()
            existing = sum(item.outcome == "skip" for item in items)
            unavailable = sum(item.outcome == "unavailable" for item in items)
            reasons = tuple(
                dict.fromkeys(item.reason for item in items if item.outcome == "unavailable")
            )
            self.status.setText(
                f"No new cards to create. {existing} already present · "
                f"{result.ignored_count} saved ignores · {unavailable} missing · "
                f"{len(result.report.unmatched)} unsupported kanji. "
                "Check Ignored cards and dictionary settings."
                + ("\n" + "\n".join(reasons) if reasons else "")
            )

    def _failed(self, error):
        self._set_busy(False)
        showWarning(f"Could not prepare kanji cards:\n{error}", parent=self)

    def reject(self):
        if not self.busy:
            self._preview_timer.stop()
            self._list_signature = None
            super().reject()


def open_manual(mw):
    ManualKanjiDialog(mw).exec()


def open_list_creation(mw, targets, source_title):
    """Open explicit category selection before the existing creation approval."""
    ManualKanjiDialog(mw, targets=targets, source_title=source_title).exec()
