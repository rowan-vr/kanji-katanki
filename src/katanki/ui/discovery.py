"""Read-only source selection, report, normalized dictionary detail, and SVG preview."""

import logging
from pathlib import Path

from aqt.operations import QueryOp
from aqt.qt import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPixmap,
    QPushButton,
    Qt,
    QTextEdit,
    QVBoxLayout,
)
from aqt.utils import showText, showWarning

from ..anki.analysis import analyze
from ..config import load_settings
from ..dictionaries.registry import bundled_path, bundled_sources, list_datasets
from .sources import SourceSelector

logger = logging.getLogger(f"addon.{__name__}")


class DiscoveryDialog(QDialog):
    def __init__(self, mw):
        super().__init__(mw)
        self.setWindowTitle("Kanji Katanki — Analyze Collection")
        self.setObjectName("katanki_discovery")
        self.resize(880, 760)
        self.mw = mw
        self.report = None
        self.busy = False
        self.sources = {}
        layout = QVBoxLayout(self)
        description = QLabel(
            "Choose deck patterns, note types, and fields. Scans are read-only.\n"
            "Deck selections include subdecks; notes with multiple cards are counted once."
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        row = QHBoxLayout()
        layout.addLayout(row)
        self.source_selector = SourceSelector(mw)
        row.addWidget(self.source_selector)
        self.source_selector.restore(load_settings(mw.col).sources)
        defaults_row = QHBoxLayout()
        layout.addLayout(defaults_row)
        self.use_bundled = QCheckBox("Use bundled default dictionaries (offline)")
        self.use_bundled.setChecked(True)
        defaults_row.addWidget(self.use_bundled)
        licenses = QPushButton("Sources and licenses…")
        licenses.clicked.connect(self._licenses)
        defaults_row.addWidget(licenses)
        for manifest in list_datasets():
            line = QHBoxLayout()
            layout.addLayout(line)
            label = QLabel(manifest.name)
            line.addWidget(label)
            entry = QLineEdit()
            entry.setAccessibleName(f"Local {manifest.name} path")
            entry.setPlaceholderText(
                "Optional override: extracted kanji/ SVG directory"
                if manifest.format == "kanjivg_svg"
                else "Optional override: local .xml or .xml.gz file"
            )
            line.addWidget(entry)
            browse = QPushButton("Browse…")
            browse.clicked.connect(
                lambda checked=False, target=entry, directory=manifest.format == "kanjivg_svg": (
                    self._browse(target, directory)
                )
            )
            line.addWidget(browse)
            self.sources[manifest.id] = entry
        self.scan_button = QPushButton("Scan selected sources")
        self.scan_button.setObjectName("katanki_scan")
        self.scan_button.clicked.connect(self._scan)
        layout.addWidget(self.scan_button)
        self.summary = QLabel("Select at least one deck and field, then scan.")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        results = QHBoxLayout()
        layout.addLayout(results, 1)
        self.characters = QListWidget()
        self.characters.setMaximumWidth(220)
        self.characters.setAccessibleName("Discovered characters")
        results.addWidget(self.characters)
        detail_column = QVBoxLayout()
        results.addLayout(detail_column, 1)
        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        detail_column.addWidget(self.detail)
        self.preview = QLabel("No stroke preview selected")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(240)
        self.preview.setStyleSheet("background: white; color: #202020;")
        detail_column.addWidget(self.preview)
        self.characters.currentTextChanged.connect(self._show_character)
        self.provenance = QTextEdit()
        self.provenance.setReadOnly(True)
        self.provenance.setMaximumHeight(100)
        self.provenance.setPlaceholderText("Dataset provenance and warnings appear after scanning.")
        layout.addWidget(self.provenance)
        self.generate_button = QPushButton("Generate cards…")
        self.generate_button.setEnabled(False)
        self.generate_button.clicked.connect(self._generate)
        layout.addWidget(self.generate_button)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        layout.addWidget(close)

    def _licenses(self):
        notice = bundled_path("bundled/NOTICE.txt").read_text(encoding="utf-8")
        for filename in ("CC-BY-SA-4.0.txt", "KanjiVG-COPYING"):
            notice += "\n\n" + bundled_path(f"bundled/licenses/{filename}").read_text(
                encoding="utf-8"
            )
        showText(
            notice, parent=self, title="Kanji Katanki — Sources and licenses", plain_text_edit=True
        )

    def _browse(self, target, directory):
        if directory:
            path = QFileDialog.getExistingDirectory(self, "Select KanjiVG kanji directory")
        else:
            path, _ = QFileDialog.getOpenFileName(
                self, "Select dictionary XML", "", "XML (*.xml *.gz)"
            )
        if path:
            target.setText(path)

    def _scan(self):
        try:
            selection = self.source_selector.selection()
            paths = bundled_sources() if self.use_bundled.isChecked() else {}
            paths.update(
                {
                    dataset_id: Path(entry.text().strip()).expanduser()
                    for dataset_id, entry in self.sources.items()
                    if entry.text().strip()
                }
            )
        except ValueError as error:
            showWarning(str(error), parent=self)
            return
        self.busy = True
        self.scan_button.setEnabled(False)
        self.generate_button.setEnabled(False)
        self.summary.setText("Scanning selected notes and loading local dictionaries…")
        QueryOp(
            parent=self.mw,
            op=lambda collection: analyze(collection, selection, paths),
            success=self._finished,
        ).failure(self._failed).with_progress("Kanji Katanki: read-only scan").run_in_background()

    def _finished(self, report):
        self.busy = False
        self.scan_button.setEnabled(True)
        self.report = report
        self.generate_button.setEnabled(bool(report.entries))
        self.characters.clear()
        self.detail.clear()
        self.preview.clear()
        supported = str(len(report.entries)) if report.dictionary_loaded else "not assessed"
        unmatched_label = "No dictionary entry" if report.dictionary_loaded else "Unclassified"
        missing_strokes = len(report.entries) - len(report.strokes)
        owned = (
            f"{report.existing_owned}/{report.missing_owned}"
            if report.existing_owned is not None
            else "not assessed"
        )
        self.summary.setText(
            f"Scanned notes: {report.scan.scanned_notes} | Distinct CJK candidates: "
            f"{len(report.scan.candidates)} | Dictionary-supported kanji: {supported}\n"
            f"{unmatched_label}: {len(report.unmatched)} | Missing stroke data: {missing_strokes}\n"
            f"Existing/missing recognition notes (supported kanji): {owned}"
        )
        self.provenance.setPlainText("\n".join((*report.warnings, *report.provenance)))
        self.characters.addItems(list(report.scan.candidates))
        if self.characters.count():
            self.characters.setCurrentRow(0)
        else:
            self.preview.setText("No ideographs found in selected fields")
        logger.info(
            "Read-only scan complete: %s notes, %s candidates",
            report.scan.scanned_notes,
            len(report.scan.candidates),
        )

    def _generate(self):
        from .generation import GenerationDialog

        if self.report and not self.busy:
            if GenerationDialog(self.mw, self.report).exec() == QDialog.DialogCode.Accepted:
                self.accept()

    def _failed(self, error):
        self.busy = False
        self.scan_button.setEnabled(True)
        self.generate_button.setEnabled(bool(self.report and self.report.entries))
        self.summary.setText("Scan failed. Previous results, if any, have been preserved.")
        logger.error("Read-only scan failed", exc_info=(type(error), error, error.__traceback__))
        showWarning(f"Kanji Katanki could not scan these sources:\n{error}", parent=self)

    def _show_character(self, character):
        if not self.report or not character:
            return
        entry = next((entry for entry in self.report.entries if entry.character == character), None)
        visual = next(
            (entry for entry in self.report.strokes if entry.character == character), None
        )
        if entry:
            text = (
                f"{character}\nMeanings: {', '.join(entry.meanings) or 'not available'}\n"
                f"On: {', '.join(entry.on_readings) or 'not available'}\n"
                f"Kun: {', '.join(entry.kun_readings) or 'not available'}\n"
                f"Strokes: {entry.stroke_count or 'not available'}\n"
                f"School grade: {entry.grade or 'not available'}"
            )
        else:
            text = (
                f"{character}\nNo dictionary entry loaded. "
                "This is not classified as supported kanji."
            )
        if visual:
            text += f"\nGraphical components: {', '.join(visual.components) or 'none listed'}"
        self.detail.setPlainText(text)
        self.preview.clear()
        if visual:
            pixmap = QPixmap()
            if pixmap.loadFromData(visual.svg, "SVG"):
                self.preview.setPixmap(pixmap)
                self.preview.setAccessibleName(f"Stroke diagram for {character}")
                return
        self.preview.setText("Stroke preview unavailable")

    def reject(self):
        # Keep callbacks alive until the serialized collection operation completes.
        if not self.busy:
            super().reject()


def open_discovery(mw):
    dialog = DiscoveryDialog(mw)
    dialog.exec()
