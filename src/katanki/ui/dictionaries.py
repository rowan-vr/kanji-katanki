"""Dataset source controls, offline checks, and attribution in Settings."""

from html import escape

from aqt.operations import QueryOp
from aqt.qt import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMenu,
    QPushButton,
    QStackedWidget,
    QTabWidget,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..config import DictionaryChoice
from ..dictionaries.preferences import check_dictionary
from ..dictionaries.registry import bundled_path, list_datasets
from ..generation.discovery import visible_text


class DictionaryPanel(QWidget):
    def __init__(self, owner, manifest, choice):
        super().__init__()
        self.owner, self.manifest = owner, manifest
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.mode = QComboBox()
        for label, value in (
            ("Bundled (offline)", "bundled"),
            ("Local file or directory", "local"),
            ("Disabled", "disabled"),
        ):
            self.mode.addItem(label, value)
        self.mode.setCurrentIndex(self.mode.findData(choice.mode))
        form.addRow("Source", self.mode)
        path_row = QHBoxLayout()
        self.path = QLineEdit(choice.path)
        self.path.setPlaceholderText(
            "SVG directory or canonical ZIP"
            if manifest.format == "kanjivg_svg"
            else "KANJIDIC2 .xml or .xml.gz"
        )
        path_row.addWidget(self.path)
        self.browse = QPushButton("Browse…")
        if manifest.format == "kanjivg_svg":
            browse_menu = QMenu(self.browse)
            browse_menu.addAction("SVG directory…").triggered.connect(lambda: self._browse(True))
            browse_menu.addAction("ZIP file…").triggered.connect(lambda: self._browse(False))
            self.browse.setMenu(browse_menu)
        else:
            self.browse.clicked.connect(lambda: self._browse(False))
        path_row.addWidget(self.browse)
        form.addRow("Local path", path_row)
        layout.addLayout(form)
        row = QHBoxLayout()
        self.check = QPushButton("Check dictionary")
        self.check.clicked.connect(self._check)
        row.addWidget(self.check)
        self.status = QLabel()
        self.status.setWordWrap(True)
        row.addWidget(self.status, 1)
        layout.addLayout(row)
        tabs = QTabWidget()
        self.about = QTextBrowser()
        self.about.setOpenExternalLinks(True)
        bundle = manifest.bundled
        metadata = (
            f"<h3>{escape(manifest.name)}</h3>"
            f"<p>{escape(', '.join(manifest.capabilities))}</p>"
            f"<p>{escape(manifest.attribution)}</p>"
            f'<p><a href="{escape(manifest.source, quote=True)}">Upstream source</a> · '
            f'<a href="{escape(manifest.license_url, quote=True)}">'
            f"{escape(manifest.license_name)}</a></p>"
        )
        if bundle:
            metadata += (
                f"<p>Bundled version: {escape(bundle['version'])}<br>"
                f"Entries: {bundle['entries']:,}<br>SHA-256:<br>"
                f"{escape(bundle['sha256'])}</p>"
            )
        metadata += (
            "<p>Local overrides keep their upstream attribution. "
            "Check a local source to see its detected version and fingerprint.</p>"
        )
        self.about.setHtml(metadata)
        tabs.addTab(self.about, "About & attribution")
        notices = QWidget()
        notices_layout = QVBoxLayout(notices)
        self.notice_files = QComboBox()
        for filename in bundle["license_files"] if bundle else ():
            self.notice_files.addItem(filename.rsplit("/", 1)[-1], filename)
        notices_layout.addWidget(self.notice_files)
        self.notice = QTextEdit()
        self.notice.setReadOnly(True)
        notices_layout.addWidget(self.notice)
        self.notice_files.currentIndexChanged.connect(self._notice_changed)
        self._notice_changed()
        tabs.addTab(notices, "License notices")
        self.check_details = QTextEdit()
        self.check_details.setReadOnly(True)
        self.check_details.setPlaceholderText(
            "Check this dictionary to see load results and provenance."
        )
        tabs.addTab(self.check_details, "Check results")
        layout.addWidget(tabs, 1)
        self.mode.currentIndexChanged.connect(self._changed)
        self.path.textChanged.connect(self._changed)
        self._changed()

    def _changed(self, *_):
        local = self.mode.currentData() == "local"
        self.path.setEnabled(local)
        self.browse.setEnabled(local)
        self.status.setText("Disabled" if self.mode.currentData() == "disabled" else "Not checked")
        self.check_details.clear()

    def _notice_changed(self, *_):
        filename = self.notice_files.currentData()
        try:
            content = (
                bundled_path(filename).read_text(encoding="utf-8")
                if filename
                else "No bundled notices."
            )
            if filename and filename.endswith(".html"):
                content = visible_text(content)
        except (OSError, ValueError) as error:
            content = f"Notice unavailable: {error}"
        self.notice.setPlainText(content)

    def _browse(self, directory=False):
        if directory:
            path = QFileDialog.getExistingDirectory(self, "Select KanjiVG kanji/ SVG directory")
        else:
            stroke = self.manifest.format == "kanjivg_svg"
            path, _ = QFileDialog.getOpenFileName(
                self,
                "Select KanjiVG ZIP" if stroke else "Select KANJIDIC2",
                "",
                "ZIP (*.zip)" if stroke else "XML (*.xml *.gz)",
            )
        if path:
            self.path.setText(path)

    def choice(self):
        return DictionaryChoice(self.manifest.id, self.mode.currentData(), self.path.text().strip())

    def _check(self):
        if self.owner.busy:
            return
        try:
            choice = self.choice()
        except ValueError as error:
            self.status.setText(str(error))
            return
        self.owner._set_testing(True)
        self.owner.dictionary_panel.setEnabled(False)
        self.status.setText("Checking…")
        QueryOp(
            parent=self.owner.mw, op=lambda _: check_dictionary(choice), success=self._checked
        ).failure(self._failed).with_progress("Katanki: checking dictionary").run_in_background()

    def _done(self):
        self.owner._set_testing(False)
        self.owner.dictionary_panel.setEnabled(True)

    def _checked(self, details):
        self._done()
        self.status.setText("Disabled" if self.mode.currentData() == "disabled" else "Check passed")
        self.check_details.setPlainText(details)

    def _failed(self, error):
        self._done()
        self.status.setText("Check failed — see Check results")
        self.check_details.setPlainText(str(error))


class DictionarySettingsPanel(QWidget):
    def __init__(self, owner, choices):
        super().__init__()
        selected = {choice.dataset_id: choice for choice in choices}
        manifests = list_datasets()
        if selected.keys() - {manifest.id for manifest in manifests}:
            raise ValueError("Unknown saved dictionary selection. Settings were preserved.")
        layout = QHBoxLayout(self)
        names = QListWidget()
        names.setMaximumWidth(155)
        names.setAccessibleName("Dictionaries")
        layout.addWidget(names)
        stack = QStackedWidget()
        layout.addWidget(stack, 1)
        self.panels = {}
        for manifest in manifests:
            names.addItem(manifest.name)
            panel = DictionaryPanel(
                owner, manifest, selected.get(manifest.id, DictionaryChoice(manifest.id))
            )
            self.panels[manifest.id] = panel
            stack.addWidget(panel)
        names.currentRowChanged.connect(stack.setCurrentIndex)
        names.setCurrentRow(0)

    def choices(self):
        return tuple(panel.choice() for panel in self.panels.values())
