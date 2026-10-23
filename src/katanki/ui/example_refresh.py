"""Explicit before/after review for legacy notes without generated-value baselines."""

from aqt.qt import QDialog, QDialogButtonBox, QLabel, QPlainTextEdit, QVBoxLayout


def review_migration(mw, updates):
    dialog = QDialog(mw)
    dialog.setWindowTitle("Katanki — Migrate existing examples")
    dialog.resize(800, 600)
    layout = QVBoxLayout(dialog)
    label = QLabel(
        "These notes have no recorded generated values. Review the replacements below. "
        "Migration replaces only the listed managed fields. UserExamples, scheduling, "
        "tags and decks are preserved. Cancel leaves these legacy notes unchanged."
    )
    label.setWordWrap(True)
    layout.addWidget(label)
    details = QPlainTextEdit()
    details.setReadOnly(True)
    rows = []
    for update in updates:
        rows.append(f"Note {update.note_id} · {update.identity.key} · {update.identity.note_type}")
        before = dict(update.before)
        for field, value in update.after:
            if field != "KatankiExamplesState" and before.get(field, "") != value:
                rows.extend((f"{field} BEFORE:\n{before.get(field, '')}", f"AFTER:\n{value}"))
        rows.append("")
    details.setPlainText("\n".join(rows))
    layout.addWidget(details)
    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Migrate examples")
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    return dialog.exec() == QDialog.DialogCode.Accepted
