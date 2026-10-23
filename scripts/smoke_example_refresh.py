"""Exercise source changes, example refresh, conflicts and Undo with real Anki APIs."""

import sys
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main():
    from anki.collection import Collection

    from katanki.anki.example_refresh import apply_example_refresh
    from katanki.anki.generation import apply_generation, preview_generation
    from katanki.anki.refresh import apply_refresh_examples, prepare_refresh
    from katanki.config import DictionaryChoice, Settings, SourceRule, save_settings
    from katanki.generation.examples import STATE_FIELD

    with TemporaryDirectory(prefix="katanki-example-refresh-") as directory:
        col = Collection(str(Path(directory) / "collection.anki2"))
        try:
            source_deck = col.decks.id("Source")
            basic = col.models.by_name("Basic")
            source = col.new_note(basic)
            source["Front"] = "景色"
            col.add_note(source, source_deck)
            settings = Settings(
                sources=(SourceRule("Source", basic["id"], ("Front",), (source_deck,)),),
                dictionaries=(
                    DictionaryChoice(
                        "kanjidic2", "local", str(ROOT / "tests/fixtures/kanjidic2.xml")
                    ),
                    DictionaryChoice("kanjivg", "local", str(ROOT / "tests/fixtures/kanjivg")),
                ),
            )
            save_settings(col, settings)
            report = prepare_refresh(col, settings).report
            preview = preview_generation(
                col, report, recognition=("景", "色"), production=("景",), include_primitives=False
            )
            apply_generation(col, preview, deck_id=1)
            generated = col.find_notes("-deck:Source")
            production = next(
                col.get_note(nid)
                for nid in generated
                if col.get_note(nid).note_type()["katanki_note_type"] == "kanji-production"
            )
            production["UserExamples"] = "<div>景景</div><div>風景</div>"
            production.tags = ["keep-my-tag"]
            col.update_note(production)
            source["Front"] = "景色<br>風景"
            col.update_note(source)
            before = {
                table: col.db.all(f"select * from {table} order by id")
                for table in ("notes", "cards", "revlog")
            }
            refresh_result = prepare_refresh(col, settings)
            plan = refresh_result.examples
            assert plan.updates and not plan.conflicts
            result = apply_refresh_examples(col, refresh_result, settings)
            assert result.updated == 2
            updated = col.get_note(production.id)
            assert updated["Prompt"].endswith("____<br>風__<br>__色")
            assert updated["UserExamples"] == production["UserExamples"]
            assert updated.tags == ["keep-my-tag"]
            for table in ("cards", "revlog"):
                assert col.db.all(f"select * from {table} order by id") == before[table]
            col.undo()
            for table in before:
                assert col.db.all(f"select * from {table} order by id") == before[table]
            apply_example_refresh(col, prepare_refresh(col, settings).examples)
            assert not prepare_refresh(col, settings).examples.updates
            disabled = replace(settings, refresh=replace(settings.refresh, update_examples=False))
            assert not prepare_refresh(col, disabled).examples.updates
            # Manual edits to managed fields are preserved and reported.
            edited = col.get_note(production.id)
            edited["VocabExamples"] = "My managed edit"
            col.update_note(edited)
            assert any(
                "manually edited" in c for c in prepare_refresh(col, settings).examples.conflicts
            )
            # Legacy notes are not adopted silently, even if their current examples match.
            legacy = next(col.get_note(nid) for nid in generated if nid != production.id)
            legacy[STATE_FIELD] = ""
            col.update_note(legacy)
            plan = prepare_refresh(col, settings).examples
            assert any(update.migration for update in plan.updates)
            assert apply_example_refresh(col, plan).updated == 0
            assert apply_example_refresh(col, plan, migrate=True).updated == 1
            # All sources can disappear. Generated notes/cards survive and recognition clears.
            col.remove_notes([source.id])
            plan = prepare_refresh(col, settings).examples
            apply_example_refresh(col, plan)
            assert set(col.find_notes("")) == set(generated)
            for nid in generated:
                note = col.get_note(nid)
                if note.note_type()["katanki_note_type"] == "kanji-recognition":
                    assert note["VocabExamples"] == ""
            print("PASS: example refresh source changes, edits, scheduling, migration and Undo")
        finally:
            col.close()


if __name__ == "__main__":
    main()
