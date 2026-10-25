"""Explicit kanji entry using the configured generation and creation review."""

from aqt.operations import QueryOp
from aqt.qt import QCheckBox, QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout
from aqt.utils import showWarning

from ..anki.refresh import prepare_manual, prepare_targets
from ..config import load_settings
from ..generation.discovery import extract_candidates
from .generation import CreationReviewDialog


class ManualKanjiDialog(QDialog):
    def __init__(self, mw, *, targets=None, source_title=""):
        super().__init__(mw)
        self.mw = mw
        self.targets = tuple(targets) if targets is not None else None
        self.busy = False
        self.setWindowTitle("Katanki — New Kanji Cards")
        self.resize(520, 340)
        layout = QVBoxLayout(self)
        hint = QLabel(
            "Paste or type kanji below. Repeated kanji and non-kanji text are ignored. "
            "Select the card types to create below. Automatic generation can stay off. "
            "Production examples come from Jitendex, not the entered text. "
            "Your deck, tag, and card settings still apply."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.text = QPlainTextEdit()
        self.text.setAccessibleName("Kanji to add")
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
        self.text.textChanged.connect(self._update)
        self._update()

    def _update(self, *_):
        count = len(extract_candidates(self.text.toPlainText()))
        selected = any(button.isChecked() for button in self.type_buttons.values())
        for button in self.type_buttons.values():
            button.setEnabled(not self.busy)
        self.create_button.setEnabled(bool(count) and selected and not self.busy)
        self.status.setText(
            f"{count:,} unique kanji" if selected else "Select at least one card type."
        )

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
        try:
            settings = load_settings(self.mw.col)
            text = self.text.toPlainText()
            prepare = prepare_targets if self.targets is not None else prepare_manual
            candidates = self.targets if self.targets is not None else text
            categories = tuple(
                kind for kind, button in self.type_buttons.items() if button.isChecked()
            )
            self._set_busy(True)
            QueryOp(
                parent=self.mw,
                op=lambda collection: prepare(
                    collection, settings, candidates, categories=categories, progress=self._progress
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
            super().reject()


def open_manual(mw):
    ManualKanjiDialog(mw).exec()


def open_list_creation(mw, targets, source_title):
    """Open explicit category selection before the existing creation approval."""
    ManualKanjiDialog(mw, targets=targets, source_title=source_title).exec()
