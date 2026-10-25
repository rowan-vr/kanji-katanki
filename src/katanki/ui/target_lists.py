"""Profile-local personal target-list management with explicit import review."""

from pathlib import Path

from aqt.qt import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    Qt,
    QVBoxLayout,
    QWidget,
)


def describe_target_list(target):
    """Plain text only: list metadata is supplied by imported files."""
    source = target.source
    lines = [
        f"{target.title} ({target.id})",
        f"Version: {target.version} · Kind: {target.kind}",
        f"Unique kanji: {len(target.characters()):,}",
        "",
        "Groups:",
        *(f"  {group.title} ({group.id}): {len(group.characters):,}" for group in target.groups),
        "",
        f"Source: {source.title}",
        f"Authority: {source.authority}",
        f"Revision: {source.revision}",
        f"License: {source.license}",
        f"Attribution: {source.attribution}",
        f"URL: {source.url or 'Not supplied'}",
    ]
    if source.sha256:
        lines.append(f"Source SHA-256: {source.sha256}")
    return "\n".join(lines)


class PersonalTargetListsPanel(QWidget):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.collection = getattr(getattr(owner, "mw", None), "col", None)
        self.store = None
        self.targets = ()
        layout = QVBoxLayout(self)
        note = QLabel(
            "Personal lists are stored locally for this Anki profile and are not synced. "
            "Import and remove apply immediately; Cancel in Settings does not undo them. "
            "Export a JSON backup to move a list to another profile or device."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        row = QHBoxLayout()
        self.names = QListWidget()
        self.names.setAccessibleName("Personal target lists")
        self.names.currentRowChanged.connect(self._selection_changed)
        row.addWidget(self.names, 1)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setAccessibleName("Personal list details and provenance")
        row.addWidget(self.details, 2)
        layout.addLayout(row, 1)
        controls = QHBoxLayout()
        self.import_button = QPushButton("Import JSON…")
        self.import_button.clicked.connect(self._import)
        controls.addWidget(self.import_button)
        self.export_button = QPushButton("Export selected…")
        self.export_button.clicked.connect(self._export)
        controls.addWidget(self.export_button)
        self.remove_button = QPushButton("Remove selected…")
        self.remove_button.clicked.connect(self._remove)
        controls.addWidget(self.remove_button)
        layout.addLayout(controls)
        self.status = QLabel()
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        try:
            if self.collection is None or not getattr(self.collection, "path", None):
                raise ValueError("Open an Anki profile to manage personal lists.")
            from ..anki.target_lists import get_personal_target_store

            self.store = get_personal_target_store(owner.mw)
            self._reload()
        except (OSError, ValueError) as error:
            self.status.setText(str(error))
            self.import_button.setEnabled(False)
        self._selection_changed()

    def _active(self):
        return (
            self.store is not None
            and self.owner.mw.col is self.collection
            and not getattr(self.owner, "busy", False)
        )

    def _selected(self):
        index = self.names.currentRow()
        return self.targets[index] if 0 <= index < len(self.targets) else None

    def _reload(self, selected_id=None):
        self.targets = self.store.load()
        self.names.clear()
        for target in self.targets:
            self.names.addItem(f"{target.title} ({target.id})")
        index = next((i for i, target in enumerate(self.targets) if target.id == selected_id), 0)
        self.names.setCurrentRow(index if self.targets else -1)
        self._selection_changed()

    def _selection_changed(self, *_):
        target = self._selected()
        self.export_button.setEnabled(target is not None)
        self.remove_button.setEnabled(target is not None)
        self.details.setPlainText(
            describe_target_list(target)
            if target
            else "No personal list selected. Import a versioned target-list JSON file."
        )

    def _notify_changed(self):
        callback = getattr(self.owner.mw, "_katanki_statistics", None)
        if callback is not None and hasattr(callback, "reload"):
            callback.reload()

    def _reserved_ids(self):
        from ..config import load_settings
        from ..dictionaries.registry import list_datasets
        from ..stats.sources import load_target_registry

        registry = load_target_registry(choices=load_settings(self.collection).dictionaries)
        return {
            manifest.id for manifest in list_datasets() if "target_lists" in manifest.capabilities
        } | {target.id for target in registry.lists}

    def _import(self):
        if not self._active():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Import personal target list", "", "JSON (*.json)"
        )
        if not path:
            return
        try:
            preview = self.store.preview(Path(path), reserved_ids=self._reserved_ids())
            target = preview.loaded.target_list
            text = describe_target_list(target)
            if preview.existing is not None:
                text += (
                    f"\n\nReplaces: {preview.existing.title} (version {preview.existing.version})"
                )
            text += (
                f"\n\nAdded kanji: {len(preview.added):,}"
                f"\nRemoved kanji: {len(preview.removed):,}"
                f"\nAdded: {''.join(preview.added) or 'None'}"
                f"\nRemoved: {''.join(preview.removed) or 'None'}"
                "\n\nWarnings:\n" + ("\n".join(preview.loaded.warnings) or "None")
            )
            if not self._review(text, replacing=preview.existing is not None):
                return
            if not self._active():
                return
            self.store.install(preview, replace=preview.existing is not None)
            self._reload(target.id)
            self.status.setText(
                f"Saved {target.title} in this profile. Existing cards are unchanged."
            )
            self._notify_changed()
        except (OSError, ValueError) as error:
            self.status.setText(f"Import failed: {error}")

    def _review(self, text, *, replacing):
        dialog = QDialog(self)
        dialog.setWindowTitle("Review personal list import")
        dialog.resize(650, 600)
        layout = QVBoxLayout(dialog)
        details = QPlainTextEdit()
        details.setReadOnly(True)
        details.setPlainText(text)
        layout.addWidget(details)
        note = QLabel("Confirming saves immediately to this profile.")
        layout.addWidget(note)
        row = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(dialog.reject)
        row.addWidget(cancel)
        apply = QPushButton("Replace existing list" if replacing else "Import list")
        apply.clicked.connect(dialog.accept)
        row.addWidget(apply)
        layout.addLayout(row)
        return dialog.exec() == QDialog.DialogCode.Accepted

    def _export(self):
        target = self._selected()
        if target is None or not self._active():
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export personal target list", f"{target.id}.json", "JSON (*.json)"
        )
        if not path:
            return
        try:
            self.store.export(target.id, Path(path))
            self.status.setText(f"Exported {target.title}.")
        except (OSError, ValueError) as error:
            self.status.setText(f"Export failed: {error}")

    def _remove(self):
        target = self._selected()
        if target is None or not self._active():
            return
        prompt = QMessageBox(self)
        prompt.setWindowTitle("Remove personal list")
        prompt.setTextFormat(Qt.TextFormat.PlainText)
        prompt.setText(
            f"Remove {target.title} ({target.id}) from this profile?\n\n"
            "This applies immediately. Existing cards are unchanged."
        )
        remove = prompt.addButton("Remove list", QMessageBox.ButtonRole.DestructiveRole)
        prompt.addButton(QMessageBox.StandardButton.Cancel)
        prompt.exec()
        if prompt.clickedButton() != remove or not self._active():
            return
        try:
            self.store.remove(target.id)
            self._reload()
            self.status.setText(f"Removed {target.title} from this profile.")
            self._notify_changed()
        except (OSError, ValueError) as error:
            self.status.setText(f"Remove failed: {error}")
