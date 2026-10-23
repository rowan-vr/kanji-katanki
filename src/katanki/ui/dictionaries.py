"""Dataset source controls, offline checks, and attribution in Settings."""

from datetime import datetime
from html import escape

from aqt.operations import QueryOp
from aqt.qt import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    Qt,
    QTabWidget,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..config import DictionaryChoice
from ..dictionaries import updates
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
            ("Default (installed update or bundled offline)", "bundled"),
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
            else "Jitendex Yomitan .zip"
            if manifest.format == "jitendex_yomitan"
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
        update_row = QHBoxLayout()
        self.update_button = QPushButton("Update dictionary")
        self.update_button.clicked.connect(self._update)
        update_row.addWidget(self.update_button)
        self.bundled_button = QPushButton("Use bundled version")
        self.bundled_button.clicked.connect(self._use_bundled)
        update_row.addWidget(self.bundled_button)
        layout.addLayout(update_row)
        self.update_status = QLabel()
        self.update_status.setWordWrap(True)
        layout.addWidget(self.update_status)
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
        if manifest.format == "jitendex_yomitan":
            metadata += (
                "<p>Default word suggestions prefer common contemporary forms, ordered by "
                "dictionary priority, then shorter words and spelling. Rare, obsolete and "
                "kana-preferred entries are excluded from suggestions. Your source vocabulary "
                "comes first. The full dictionary remains available offline.</p>"
                "<p>Local overrides must be Jitendex-compatible Yomitan ZIP files. "
                "Use Cards → Discovered and default words to include dictionary examples.</p>"
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

    def refresh_updates(self):
        current = updates.installed(self.manifest)
        bundle = current[1]["bundled"] if current else self.manifest.bundled
        source = "Downloaded" if current else "Bundled"
        release = updates.available(self.manifest)
        text = f"{source} version: {bundle['version']}"
        if release:
            text += f" · Update available: {release['version']}"
        else:
            text += " · No newer compatible version in the cached catalog"
        self.update_status.setText(text)
        enabled = self.mode.currentData() == "bundled"
        self.update_button.setEnabled(enabled and release is not None)
        self.bundled_button.setEnabled(enabled and current is not None)
        previous = self.notice_files.currentData()
        self.notice_files.blockSignals(True)
        self.notice_files.clear()
        for filename in bundle["license_files"]:
            self.notice_files.addItem(filename.rsplit("/", 1)[-1], filename)
        index = self.notice_files.findData(previous)
        self.notice_files.setCurrentIndex(max(0, index))
        self.notice_files.blockSignals(False)
        self._notice_changed()

    def _update(self):
        if self.owner.busy or self.mode.currentData() != "bundled":
            return
        release = updates.available(self.manifest)
        if release is None:
            return
        self.owner._set_testing(True)
        self.update_status.setText("Downloading and validating dictionary…")
        QueryOp(
            parent=self.owner.mw,
            op=lambda _: updates.install(self.manifest, release),
            success=self._updated,
        ).without_collection().failure(self._update_failed).with_progress(
            "Katanki: downloading and validating dictionary"
        ).run_in_background()

    def _updated(self, version):
        self._done()
        self.refresh_updates()
        self.status.setText(f"Installed {version}. Future refreshes will use this version.")
        self.check_details.clear()

    def _update_failed(self, error):
        self._done()
        self.refresh_updates()
        self.status.setText("Update failed; existing dictionaries were preserved")
        self.check_details.setPlainText(str(error))

    def _use_bundled(self):
        if self.owner.busy:
            return
        try:
            updates.use_bundled(self.manifest.id)
            self.refresh_updates()
            self.status.setText("Using bundled defaults for future refreshes")
        except (OSError, ValueError) as error:
            self.status.setText(str(error))

    def _changed(self, *_):
        local = self.mode.currentData() == "local"
        self.path.setEnabled(local)
        self.browse.setEnabled(local)
        self.status.setText("Disabled" if self.mode.currentData() == "disabled" else "Not checked")
        self.check_details.clear()
        self.refresh_updates()

    def _notice_changed(self, *_):
        filename = self.notice_files.currentData()
        try:
            current = updates.installed(self.manifest)
            content = (
                bundled_path(filename, current[0] if current else None).read_text(encoding="utf-8")
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
            words = self.manifest.format == "jitendex_yomitan"
            path, _ = QFileDialog.getOpenFileName(
                self,
                "Select Jitendex Yomitan ZIP"
                if words
                else "Select KanjiVG ZIP"
                if stroke
                else "Select KANJIDIC2",
                "",
                "ZIP (*.zip)" if stroke or words else "XML (*.xml *.gz)",
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
        self.owner = owner
        selected = {choice.dataset_id: choice for choice in choices}
        manifests = list_datasets()
        if selected.keys() - {manifest.id for manifest in manifests}:
            raise ValueError("Unknown saved dictionary selection. Settings were preserved.")
        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.check_updates_button = QPushButton("Check for dictionary updates")
        self.check_updates_button.clicked.connect(self._check_updates)
        controls.addWidget(self.check_updates_button)
        self.automatic = QCheckBox("Check daily on startup")
        self.automatic.setChecked(updates.preferences().get("automatic", False))
        controls.addWidget(self.automatic)
        layout.addLayout(controls)
        self.update_status = QLabel()
        self.update_status.setWordWrap(True)
        layout.addWidget(self.update_status)
        hint = QLabel(
            "Dictionary downloads and returning to bundled data apply immediately. "
            "Existing notes are unchanged. Offline use does not require an update check."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        content = QHBoxLayout()
        layout.addLayout(content, 1)
        names = QListWidget()
        names.setMaximumWidth(155)
        names.setAccessibleName("Dictionaries")
        content.addWidget(names)
        stack = QStackedWidget()
        content.addWidget(stack, 1)
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
        self._show_last_check()

    def _show_last_check(self):
        state = updates.preferences()
        timestamp = state.get("last_success")
        text = (
            "Last successful check: " + datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")
            if timestamp
            else "Dictionary updates have not been checked."
        )
        if state.get("error"):
            text += " · Last attempt failed; installed dictionaries remain available."
        self.update_status.setText(text)

    def _check_updates(self):
        if self.owner.busy:
            return
        self.owner._set_testing(True)
        self.update_status.setText("Checking for dictionary updates…")
        QueryOp(
            parent=self.owner.mw, op=lambda _: updates.check_updates(), success=self._checked
        ).without_collection().failure(self._failed).with_progress(
            "Katanki: checking dictionary updates"
        ).run_in_background()

    def _checked(self, catalog):
        self.owner._set_testing(False)
        self._show_last_check()
        available = [
            panel.manifest.name
            for panel in self.panels.values()
            if updates.available(panel.manifest, catalog)
        ]
        result = (
            "Check complete: updates available for " + ", ".join(available) + "."
            if available
            else "Check complete: no dictionary updates available."
        )
        self.update_status.setText(result + "\n" + self.update_status.text())
        for panel in self.panels.values():
            panel.refresh_updates()
        candidates = [
            (panel, release)
            for panel in self.panels.values()
            if (release := updates.available(panel.manifest, catalog))
        ]
        if not candidates:
            self._show_result("All dictionaries are up to date.")
            return
        eligible = [
            (panel.manifest, release)
            for panel, release in candidates
            if panel.mode.currentData() == "bundled"
        ]
        text = "Dictionary updates are available:\n\n" + "\n".join(
            f"• {panel.manifest.name}: {release['version']}" for panel, release in candidates
        )
        if len(eligible) != len(candidates):
            text += (
                "\n\nOnly dictionaries using the Default source will be updated. "
                "Choose Default to update a local or disabled dictionary."
            )
        self._show_result(text, candidates=eligible)

    def _show_result(self, text, *, failed=False, candidates=()):
        popup = QMessageBox(self.owner)
        popup.setObjectName("katanki_dictionary_update_result")
        popup.setWindowTitle("Katanki — Dictionary updates")
        popup.setIcon(QMessageBox.Icon.Warning if failed else QMessageBox.Icon.Information)
        popup.setTextFormat(Qt.TextFormat.PlainText)
        popup.setText(text)
        update_button = (
            popup.addButton("Update", QMessageBox.ButtonRole.AcceptRole) if candidates else None
        )
        popup.addButton(QMessageBox.StandardButton.Close)
        popup.exec()
        if update_button is not None and popup.clickedButton() == update_button:
            self._install_updates(candidates)

    def _install_updates(self, candidates):
        if self.owner.busy:
            return

        def install(_):
            results = []
            for manifest, release in candidates:
                try:
                    version = updates.install(manifest, release)
                    results.append((manifest.name, version, ""))
                except Exception as error:
                    results.append((manifest.name, "", str(error)))
            return results

        self.owner._set_testing(True)
        self.update_status.setText("Downloading and validating dictionary updates…")
        QueryOp(
            parent=self.owner.mw, op=install, success=self._installed
        ).without_collection().failure(self._install_failed).with_progress(
            "Katanki: downloading dictionary updates"
        ).run_in_background()

    def _installed(self, results):
        self.owner._set_testing(False)
        for panel in self.panels.values():
            panel.refresh_updates()
            panel.check_details.clear()
        failed = any(error for _, _, error in results)
        text = "\n".join(
            f"{name}: update failed — {error}" if error else f"{name}: updated to {version}"
            for name, version, error in results
        )
        if failed:
            text += "\n\nDictionaries whose updates failed keep their previous data."
        else:
            text += "\n\nFuture refreshes will use the updated dictionaries."
        self.update_status.setText(text)
        self._show_result(text, failed=failed)

    def _install_failed(self, error):
        self.owner._set_testing(False)
        for panel in self.panels.values():
            panel.refresh_updates()
        text = f"Dictionary update failed:\n\n{error}\n\nInstalled dictionaries remain available."
        self.update_status.setText(text)
        self._show_result(text, failed=True)

    def _failed(self, error):
        self.owner._set_testing(False)
        self.update_status.setText(f"Update check failed: {error}. Offline data remains available.")
        self._show_result(
            f"Update check failed:\n\n{error}\n\n"
            "Your existing dictionaries remain available offline.",
            failed=True,
        )

    def save_preferences(self):
        updates.set_automatic(self.automatic.isChecked())

    def choices(self):
        return tuple(panel.choice() for panel in self.panels.values())
