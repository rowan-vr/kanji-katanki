"""Explicit kanji entry using the configured generation and creation review."""

from aqt.operations import QueryOp
from aqt.qt import QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout
from aqt.utils import showWarning

from ..anki.refresh import prepare_manual
from ..config import load_settings
from ..generation.discovery import extract_candidates
from .generation import CreationReviewDialog


class ManualKanjiDialog(QDialog):
    def __init__(self, mw):
        super().__init__(mw)
        self.mw = mw
        self.busy = False
        self.setWindowTitle("Katanki — New Kanji Cards")
        self.resize(520, 340)
        layout = QVBoxLayout(self)
        hint = QLabel(
            "Paste or type kanji below. Repeated kanji and non-kanji text are ignored. "
            "Cards use your enabled Generation categories, decks, tags, and Cards settings."
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
        row = QHBoxLayout()
        self.cancel = QPushButton("Cancel")
        self.cancel.clicked.connect(self.reject)
        row.addWidget(self.cancel)
        row.addStretch()
        self.preview_button = QPushButton("Review new cards")
        self.preview_button.clicked.connect(self._preview)
        row.addWidget(self.preview_button)
        layout.addLayout(row)
        self.text.textChanged.connect(self._update)
        self._update()

    def _update(self):
        count = len(extract_candidates(self.text.toPlainText()))
        self.preview_button.setEnabled(bool(count) and not self.busy)
        self.status.setText(f"{count:,} unique kanji")

    def _set_busy(self, busy):
        self.busy = busy
        self.text.setEnabled(not busy)
        self.cancel.setEnabled(not busy)
        self._update()

    def _preview(self):
        if self.busy or not self.preview_button.isEnabled():
            return
        try:
            settings = load_settings(self.mw.col)
            text = self.text.toPlainText()
            self._set_busy(True)
            QueryOp(
                parent=self.mw,
                op=lambda collection: prepare_manual(collection, settings, text),
                success=self._finished,
            ).failure(self._failed).with_progress(
                "Katanki: preparing kanji cards"
            ).run_in_background()
        except Exception as error:
            self._failed(error)

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
            self.status.setText(
                f"No new cards to create. {existing} already present · "
                f"{result.ignored_count} saved ignores · {unavailable} unavailable · "
                f"{len(result.report.unmatched)} unsupported kanji. "
                "Check enabled Generation categories and Ignored cards in Settings."
            )

    def _failed(self, error):
        self._set_busy(False)
        showWarning(f"Could not prepare kanji cards:\n{error}", parent=self)

    def reject(self):
        if not self.busy:
            super().reject()


def open_manual(mw):
    ManualKanjiDialog(mw).exec()
