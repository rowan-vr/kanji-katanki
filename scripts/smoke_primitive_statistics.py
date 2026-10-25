"""Read-only Parts evidence and native Qt rendering against a temporary Anki collection."""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def main():
    from anki.collection import Collection
    from aqt.qt import QApplication, QWidget

    from katanki.anki.identities import MODEL_MARKER
    from katanki.anki.primitive_statistics import primitive_snapshot
    from katanki.ui.primitive_statistics import PrimitiveStatisticsDialog

    app = QApplication.instance() or QApplication([])
    with TemporaryDirectory() as directory:
        col = Collection(str(Path(directory) / "collection.anki2"))
        model = col.models.new("Parts smoke")
        model[MODEL_MARKER] = "primitive-recognition"
        col.models.add_field(model, col.models.new_field("Component"))
        template = col.models.new_template("Card")
        template.update(qfmt="{{Component}}", afmt="{{FrontSide}}")
        col.models.add_template(model, template)
        col.models.add(model)
        note = col.new_note(model)
        note["Component"] = "graphical:smoke"
        col.add_note(note, 1)
        card = note.cards()[0]
        card.type, card.ivl, card.queue = 2, 30, -1
        col.update_card(card)
        before = col.db.all("select * from cards"), col.db.all("select * from notes")
        snapshot = primitive_snapshot(col)
        assert snapshot[0].state("graphical:smoke", "recognition") == "mature"
        assert snapshot[0].state("graphical:smoke", "writing") == "missing"
        window = QWidget()
        window.col = col
        with patch("katanki.ui.primitive_statistics.QueryOp") as query:
            query.return_value.failure.return_value = SimpleNamespace(
                run_in_background=lambda: None
            )
            dialog = PrimitiveStatisticsDialog(window)
            dialog.loaded(snapshot)
            dialog.search.setText("graphical:smoke")
            assert dialog.table.rowCount() == 1
            assert dialog.table.item(0, 2).text() == "Mature"
            dialog.mode.setCurrentIndex(1)
            assert dialog.table.item(0, 2).text() == "Missing"
            dialog.close()
        assert before == (col.db.all("select * from cards"), col.db.all("select * from notes"))
        col.close()
        window.close()
        app.processEvents()
    print("PASS: real Anki Parts ownership, native Qt modes, unchanged collection")


if __name__ == "__main__":
    main()
