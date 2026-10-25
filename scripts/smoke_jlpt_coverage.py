"""Verify bundled modern JLPT targets and native coverage against temporary Anki data."""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


def fixture(collection, target):
    from katanki.anki.identities import MODEL_MARKER

    for mode in ("recognition", "production"):
        model = collection.models.new(f"JLPT smoke {mode}")
        model[MODEL_MARKER] = f"kanji-{mode}"
        collection.models.add_field(model, collection.models.new_field("Character"))
        template = collection.models.new_template("Card")
        template.update(qfmt="{{Character}}", afmt="{{FrontSide}}")
        collection.models.add_template(model, template)
        collection.models.add(model)
        for group in target.groups:
            for index, character in enumerate(group.characters[:2]):
                note = collection.new_note(model)
                note["Character"] = character
                collection.add_note(note, 1)
                card = note.cards()[0]
                if mode == "recognition":
                    card.type, card.ivl, card.queue = 2, (30 if index == 0 else 10), 2
                else:
                    card.type, card.ivl, card.queue = (0, 0, 0) if index == 0 else (2, 30, 2)
                collection.update_card(card)


def main():
    from anki.collection import Collection
    from aqt.qt import QApplication, QListWidget, QWidget

    from katanki.stats.sources import load_target_registry
    from katanki.ui.dashboard import open_statistics
    from katanki.ui.datasets import DatasetSettingsPanel
    from scripts.smoke_statistics import InlineQuery, wait_for

    app = QApplication.instance() or QApplication(["katanki-jlpt-smoke"])
    registry = load_target_registry()
    target = next(target for target in registry.lists if target.id == "jlpt-openjlpt")
    assert target.source.authority == "unofficial"
    assert "unofficial" in target.title.lower()
    assert target.source.revision == "0d1d3410bec90bd4098a7c72de820543cb4f707c"
    assert "CC BY-SA 4.0" in target.source.license
    assert [group.id for group in target.groups] == ["n5", "n4", "n3", "n2", "n1"]
    assert [len(group.characters) for group in target.groups] == [84, 169, 387, 398, 1345]
    assert len(target.characters()) == 2383
    with TemporaryDirectory(prefix="katanki-jlpt-smoke-") as directory:
        mw = QWidget()
        mw.col = Collection(str(Path(directory) / "collection.anki2"))
        try:
            fixture(mw.col, target)
            tables = ("notes", "cards", "revlog")
            before = {
                table: mw.col.db.all(f"select * from {table} order by id") for table in tables
            }
            # Deliberately supply no dictionary metadata: targets must survive absent coverage.
            with (
                patch("katanki.anki.statistics.dictionary_sources", return_value={}),
                patch("katanki.ui.dashboard.QueryOp", InlineQuery),
            ):
                open_statistics(mw)
                dialog = mw._katanki_statistics
                wait_for(lambda: dialog.snapshot is not None and not dialog.loading)
                assert not dialog.snapshot[2]
                for mode in ("recognition", "writing"):
                    dialog.mode.setCurrentIndex(dialog.mode.findData(mode))
                    dialog.select_scope((target.id, None))
                    assert dialog.source.rowCount() == 2383
                    assert dialog.counts["mature"] == 5
                    assert dialog.counts["young"] == (5 if mode == "recognition" else 0)
                    for group in target.groups:
                        key = (target.id, group.id)
                        item = dialog.section_items[key]
                        bar = dialog.scope.itemWidget(item, 1)
                        assert bar.maximum() == len(group.characters)
                        assert bar.value() == (2 if mode == "recognition" else 1)
                        assert item.text(2) == "1"
                        dialog.select_scope(key)
                        assert dialog.source.rowCount() == len(group.characters)
                        assert dialog.counts["missing"] == len(group.characters) - 2
                    dialog.scope.blockSignals(True)
                    dialog.scope.clearSelection()
                    for group in target.groups[:3]:
                        dialog.section_items[(target.id, group.id)].setSelected(True)
                    dialog.scope.blockSignals(False)
                    dialog._render_scope()
                    assert dialog.source.rowCount() == 640  # N5 through N3 union.
                    assert len(set(dialog.current_targets)) == 640
                    assert dialog.counts["mature"] == 3
                dialog.close()
            panel = DatasetSettingsPanel(SimpleNamespace(mw=mw, busy=False), (), target_lists=True)
            source = panel.panels[target.id]
            assert source.mode.currentData() == "bundled"
            about = source.about.toPlainText()
            assert "unofficial" in about.lower()
            assert "OpenJLPT" in about and "CC BY-SA 4.0" in about and "2,383" in about
            names = panel.findChildren(QListWidget)
            assert any("OpenJLPT" in names[0].item(i).text() for i in range(names[0].count()))
            assert "OpenJLPT-LICENSE" in [
                source.notice_files.itemText(i) for i in range(source.notice_files.count())
            ]
            panel.close()
            after = {table: mw.col.db.all(f"select * from {table} order by id") for table in tables}
            assert before == after
        finally:
            if hasattr(mw, "_katanki_statistics"):
                mw._katanki_statistics.close()
            mw.col.close()
            mw.close()
            app.processEvents()
    print(
        "PASS: 2,383 unofficial JLPT targets; five level bars and cumulative union in both "
        "modes; absent metadata preserved; settings provenance; unchanged notes/cards/revlog"
    )


if __name__ == "__main__":
    main()
