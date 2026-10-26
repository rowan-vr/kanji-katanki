"""Verify the card-settings refresh prompt with real Qt and disposable Anki data.

Run with an Anki-capable Python and QT_QPA_PLATFORM=offscreen for headless checks.
"""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def main():
    sys.path.insert(0, str(ROOT / "src"))
    from anki.collection import Collection
    from aqt.qt import QApplication, QDialog, QMessageBox, QTimer, QWidget

    from katanki.config import DictionaryChoice, Settings, SourceRule, load_settings, save_settings
    from katanki.dictionaries import updates
    from katanki.ui.settings import SettingsDialog

    app = QApplication.instance() or QApplication([])
    with TemporaryDirectory(prefix="katanki-card-settings-") as directory:
        mw = QWidget()
        mw.col = Collection(str(Path(directory) / "collection.anki2"))
        try:
            model = mw.col.models.by_name("Basic")
            save_settings(
                mw.col,
                Settings(
                    sources=(SourceRule("*", model["id"], ("Front",)),),
                    dictionaries=tuple(
                        DictionaryChoice(name, "disabled")
                        for name in ("kanjidic2", "kanjivg", "jitendex")
                    ),
                ),
            )
            with (
                patch.object(updates, "USER_DATA", Path(directory) / "updates"),
                patch("katanki.ui.refresh.open_refresh") as refresh,
            ):
                for choice in ("Do later", "Refresh now", "unchanged", "cancel"):
                    original = load_settings(mw.col)
                    dialog = SettingsDialog(mw)
                    if choice != "unchanged":
                        panel = dialog.card_panels["recognition"]
                        panel.limit.setValue(panel.limit.value() + 1)
                    answered, errors = [], []

                    def check_popup(popup, choice, original):
                        assert popup.text() == "Your card settings have been saved."
                        assert choice in ("Do later", "Refresh now")
                        assert load_settings(mw.col).cards != original.cards

                    def respond(choice=choice, original=original, answered=answered, errors=errors):
                        popup = app.activeModalWidget()
                        if not isinstance(popup, QMessageBox):
                            return
                        try:
                            check_popup(popup, choice, original)
                            next(b for b in popup.buttons() if b.text() == choice).click()
                            answered.append(choice)
                        except Exception as error:
                            errors.append(error)
                            popup.reject()

                    poll, deadline = QTimer(), QTimer()
                    poll.timeout.connect(respond)
                    deadline.setSingleShot(True)
                    deadline.timeout.connect(dialog.reject)
                    poll.start(10)
                    deadline.start(5000)
                    QTimer.singleShot(0, dialog.reject if choice == "cancel" else dialog._save)
                    result = dialog.exec()
                    poll.stop()
                    deadline.stop()
                    app.processEvents()
                    assert not errors, errors
                    assert refresh.call_count == int(choice == "Refresh now")
                    assert answered == ([choice] if choice in ("Do later", "Refresh now") else [])
                    if choice == "cancel":
                        assert result == QDialog.DialogCode.Rejected
                        assert load_settings(mw.col) == original
                    else:
                        assert result == QDialog.DialogCode.Accepted
                    refresh.reset_mock()
        finally:
            mw.col.close()
    print("PASS: saved changes, Do later, Refresh now, unchanged Save and Cancel")


if __name__ == "__main__":
    main()
