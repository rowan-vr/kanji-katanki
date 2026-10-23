"""Persistent refresh feedback with a direct route to correcting settings."""

from aqt.qt import QDialog, QDialogButtonBox, QLabel, QPushButton, QTimer, QVBoxLayout


def source_feedback(mw, message):
    dialog = QDialog(mw)
    dialog.setWindowTitle("Katanki — Refresh needs attention")
    layout = QVBoxLayout(dialog)
    label = QLabel(message)
    label.setWordWrap(True)
    layout.addWidget(label)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    edit = QPushButton("Edit sources…")
    buttons.addButton(edit, QDialogButtonBox.ButtonRole.ActionRole)
    edit.clicked.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    if dialog.exec() != QDialog.DialogCode.Accepted or mw.col is None:
        return
    from .settings import SettingsDialog

    settings = SettingsDialog(mw)
    if settings.exec() == QDialog.DialogCode.Accepted:
        from .refresh import open_refresh

        QTimer.singleShot(0, lambda: open_refresh(mw) if mw.col is not None else None)
