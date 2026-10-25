"""Exercise personal-list import review and persistence with real Anki and Qt."""

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]


def main():
    sys.path.insert(0, str(ROOT / "src"))
    from anki.collection import Collection
    from aqt.qt import QApplication, QWidget

    from katanki.anki.target_lists import PersonalTargetStore
    from katanki.stats.targets import read_target_list
    from katanki.ui.target_lists import PersonalTargetListsPanel

    app = QApplication.instance() or QApplication([])
    with TemporaryDirectory(prefix="katanki-personal-lists-") as directory:
        root = Path(directory)
        mw = QWidget()
        mw.col = Collection(str(root / "collection.anki2"))
        store = PersonalTargetStore(root / "user_files", "profile-one")
        owner = SimpleNamespace(mw=mw, busy=False)
        payload = {
            "schema_version": 1,
            "id": "user:smoke-course",
            "title": "<Course> 日本語",
            "version": "1",
            "kind": "textbook",
            "source": {
                "title": "Personal study",
                "url": None,
                "revision": "1",
                "license": "Private study",
                "attribution": "Smoke fixture",
                "authority": "user",
            },
            "groups": [
                {"id": "one", "title": "Lesson one", "characters": ["日", "月", "日"]},
                {"id": "two", "title": "Lesson two", "characters": ["月", "火"]},
            ],
        }
        source, exported = root / "import.json", root / "export.json"

        def write_source():
            source.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

        write_source()
        try:
            before = (
                mw.col.note_count(),
                mw.col.card_count(),
                mw.col.db.scalar("select count(*) from revlog"),
            )
            with (
                patch("katanki.anki.target_lists.get_personal_target_store", return_value=store),
                patch(
                    "katanki.ui.target_lists.QFileDialog.getOpenFileName",
                    return_value=(str(source), ""),
                ),
            ):
                panel = PersonalTargetListsPanel(owner)
                panel.resize(850, 540)
                panel.show()
                app.processEvents()
                with patch.object(panel, "_review", return_value=False) as review:
                    panel._import()
                    assert "Warnings:" in review.call_args.args[0]
                    assert store.load() == ()
                with patch.object(panel, "_review", return_value=True):
                    panel._import()
                assert panel.targets[0].characters() == ("日", "月", "火")
                assert "<Course> 日本語" in panel.details.toPlainText()
                assert "Unique kanji: 3" in panel.details.toPlainText()
                assert "Private study" in panel.details.toPlainText()
                payload["version"] = "2"
                payload["groups"] = [{"id": "one", "title": "Revised", "characters": ["日", "水"]}]
                write_source()
                with patch.object(panel, "_review", return_value=False) as review:
                    panel._import()
                    assert review.call_args.kwargs["replacing"]
                    assert "Added: 水" in review.call_args.args[0]
                    assert "Removed: 月火" in review.call_args.args[0]
                    assert store.load()[0].version == "1"
                with patch.object(panel, "_review", return_value=True):
                    panel._import()
                with patch(
                    "katanki.ui.target_lists.QFileDialog.getSaveFileName",
                    return_value=(str(exported), ""),
                ):
                    panel._export()
                assert read_target_list(exported).target_list == store.load()[0]
                reopened = PersonalTargetListsPanel(owner)
                assert reopened.targets[0].version == "2"
                assert PersonalTargetStore(root / "user_files", "profile-two").load() == ()
                source.write_text('{"schema_version": 999}', encoding="utf-8")
                panel._import()
                assert "Import failed:" in panel.status.text()
                assert store.load()[0].version == "2"
                owner.busy = True
                panel._import()
                assert store.load()[0].version == "2"
                owner.busy = False
                with patch("katanki.ui.target_lists.QMessageBox") as message:
                    prompt = message.return_value
                    remove = Mock()
                    prompt.addButton.return_value = remove
                    prompt.clickedButton.return_value = None
                    panel._remove()
                    assert store.load()[0].version == "2"
                    prompt.clickedButton.return_value = remove
                    panel._remove()
                    assert store.load() == () and panel.targets == ()
                    assert not panel.remove_button.isEnabled()
                assert (
                    mw.col.note_count(),
                    mw.col.card_count(),
                    mw.col.db.scalar("select count(*) from revlog"),
                ) == before
                panel.close()
                reopened.close()
                app.processEvents()
            print(
                "Personal lists: review/cancel, replacement diff, remove/cancel, "
                "plain-text provenance, export, restart, profile isolation and "
                "unchanged collection passed."
            )
        finally:
            mw.col.close()
            mw.close()


if __name__ == "__main__":
    main()
