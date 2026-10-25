"""Exercise list planning, explicit approval, and idempotency against real Anki."""

import sys
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main():
    import anki
    from anki.collection import Collection
    from aqt.qt import QApplication, QWidget

    from katanki.anki.generation import apply_generation
    from katanki.anki.ignored import save_ignored
    from katanki.anki.refresh import prepare_targets
    from katanki.config import DictionaryChoice, GenerationSettings, Settings
    from katanki.generation.planner import Identity
    from katanki.ui.manual import ManualKanjiDialog

    app = QApplication.instance() or QApplication([])
    with TemporaryDirectory(prefix="katanki-list-creation-") as directory:
        col = Collection(str(Path(directory) / "collection.anki2"))
        mw = QWidget()
        mw.col = col
        try:
            settings = replace(
                Settings(),
                dictionaries=(
                    DictionaryChoice(
                        "kanjidic2", "local", str(ROOT / "tests/fixtures/kanjidic2.xml")
                    ),
                    DictionaryChoice("kanjivg", "local", str(ROOT / "tests/fixtures/kanjivg")),
                ),
                generation=tuple(GenerationSettings(False, 1) for _ in range(3)),
            )
            save_ignored(col, (Identity("kanji-recognition", "色"),))
            before = col.db.all("select * from notes")
            result = prepare_targets(col, settings, ("色", "景", "色"), categories=("recognition",))
            assert result.report.scan.candidates == ("色", "景")
            assert col.db.all("select * from notes") == before
            assert [item.unit.identity for item in result.preview.plan.items] == [
                Identity("kanji-recognition", "景")
            ]
            dialog = ManualKanjiDialog(mw, targets=("色", "景"), source_title="Example group")
            assert dialog.text.isReadOnly()
            assert dialog.text.toPlainText() == "色景"
            assert dialog.create_button.text() == "Review cards…"
            dialog.reject()
            assert col.db.all("select * from notes") == before
            # Simulate the explicit approval boundary through the existing writer.
            applied = apply_generation(col, result.preview)
            assert applied.created == 1
            assert apply_generation(col, result.preview).created == 0
            again = prepare_targets(col, settings, ("色", "景"), categories=("recognition",))
            assert all(item.outcome == "skip" for item in again.preview.plan.items)
        finally:
            col.close()
            mw.close()
            app.processEvents()
    print(
        f"PASS: Anki {anki.version}; Linux; list input, Qt input cancellation, "
        "ignores and idempotency"
    )


if __name__ == "__main__":
    main()
