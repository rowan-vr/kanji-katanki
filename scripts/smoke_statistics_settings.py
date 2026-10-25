"""Check separated list/dictionary settings with real Qt and disposable Anki data."""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def main():
    sys.path.insert(0, str(ROOT / "src"))
    from anki.collection import Collection
    from aqt.qt import QApplication, QWidget

    from katanki.config import DictionaryChoice, Settings, SourceRule, load_settings, save_settings
    from katanki.dictionaries import updates
    from katanki.stats.sources import load_target_registry
    from katanki.ui.settings import SettingsDialog

    app = QApplication.instance() or QApplication([])
    with TemporaryDirectory(prefix="katanki-statistics-settings-") as directory:
        mw = QWidget()
        mw.col = Collection(str(Path(directory) / "collection.anki2"))
        try:
            model = mw.col.models.by_name("Basic")
            from katanki.dictionaries.registry import bundled_path

            local = Path(directory) / "school-grades.json"
            local.write_bytes(bundled_path("bundled/school-grades.json").read_bytes())
            save_settings(
                mw.col,
                Settings(
                    sources=(SourceRule("*", model["id"], ("Front",)),),
                    dictionaries=(
                        DictionaryChoice("school-grades", "local", str(local)),
                        DictionaryChoice("kanjivg", "disabled"),
                    ),
                ),
            )
            with (
                patch.object(updates, "USER_DATA", Path(directory) / "updates"),
                patch("katanki.ui.settings.showWarning", side_effect=AssertionError),
            ):
                dialog = SettingsDialog(mw)
                assert dialog.tabs.tabText(4) == "Statistics"
                stats = dialog.statistics_panel
                assert [stats.tabs.tabText(i) for i in range(stats.tabs.count())] == [
                    "Lists",
                    "Personal lists",
                ]
                dictionaries = dialog.dictionary_panel
                assert set(dictionaries.panels) == {"kanjidic2", "kanjivg", "jitendex"}
                assert set(stats.lists.panels) == {"school-grades", "joyo"}
                target = stats.lists.panels["school-grades"]
                assert target.check.text() == "Check list"
                assert target.update_button.text() == "Update list"
                assert target.mode.currentData() == "local" and target.path.text() == str(local)
                assert "1,026" in target.about.toPlainText()
                assert "JSON" in target.path.placeholderText().upper()
                stats.lists.automatic.setChecked(True)
                assert dictionaries.automatic.isChecked()
                dictionaries.automatic.setChecked(False)
                assert not stats.lists.automatic.isChecked()
                dialog._set_testing(True)
                assert not stats.isEnabled() and not dictionaries.isEnabled()
                dialog._set_testing(False)
                assert stats.isEnabled() and dictionaries.isEnabled()
                # A catalog check on either page offers updates for that page only.
                with patch.object(updates, "available", return_value={"version": "2099-01-01"}):
                    with patch.object(stats.lists, "_show_result") as result:
                        stats.lists._checked({})
                        text = result.call_args.args[0]
                        assert "School grades" in text and "Jitendex" not in text
                        assert (
                            all(m.id == "joyo" for m, _ in result.call_args.kwargs["candidates"])
                            is True
                        )
                        # Local overrides are listed, but never updated automatically.
                        assert [m.id for m, _ in result.call_args.kwargs["candidates"]] == ["joyo"]
                    with patch.object(dictionaries, "_show_result") as result:
                        dictionaries._checked({})
                        assert "School grades" not in result.call_args.args[0]
                        assert all(
                            m.id not in {"school-grades", "joyo"}
                            for m, _ in result.call_args.kwargs["candidates"]
                        )
                dialog._save()
                saved = load_settings(mw.col)
                assert len(saved.dictionaries) == 5
                assert next(
                    c for c in saved.dictionaries if c.dataset_id == "school-grades"
                ).path == str(local)
                reopened = SettingsDialog(mw)
                assert reopened.statistics_panel.choices() == stats.choices()
                assert reopened.dictionary_panel.choices() == dictionaries.choices()
                assert not updates.preferences()["automatic"]
                list_panel = reopened.statistics_panel.lists.panels["school-grades"]
                list_panel.mode.setCurrentIndex(list_panel.mode.findData("disabled"))
                reopened.reject()
                assert load_settings(mw.col) == saved
                assert (
                    len(
                        next(
                            t
                            for t in load_target_registry(choices=saved.dictionaries).lists
                            if t.id == "school-grades"
                        ).characters()
                    )
                    == 1026
                )
                assert mw.col.note_count() == 0 and mw.col.card_count() == 0
                dialog.close()
                reopened.close()
                app.processEvents()
            print(
                "Statistics → Lists: separation, labels, filtering, busy controls, "
                "persistence and cancel passed."
            )
        finally:
            mw.col.close()
            mw.close()


if __name__ == "__main__":
    main()
