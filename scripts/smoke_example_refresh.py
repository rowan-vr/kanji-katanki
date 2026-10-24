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
            # Managed edits and missing tracking are replaced without a review.
            edited = col.get_note(production.id)
            edited["VocabExamples"] = "My managed edit"
            col.update_note(edited)
            legacy = next(col.get_note(nid) for nid in generated if nid != production.id)
            legacy[STATE_FIELD] = ""
            col.update_note(legacy)
            plan = prepare_refresh(col, settings).examples
            assert not plan.conflicts and all(not update.migration for update in plan.updates)
            assert apply_example_refresh(col, plan).updated == 2
            # Editor-damaged tracking is replaced automatically with Undo support.
            damaged = col.get_note(production.id)
            damaged[STATE_FIELD] = (
                '{"version": 1, "fields": {"VocabExamples": '
                '"<div data-source="\\&quot;vocabulary\\&quot;">景色</div>"}}'
            )
            col.update_note(damaged)
            damaged_snapshot = {
                table: col.db.all(f"select * from {table} order by id")
                for table in ("notes", "cards", "revlog")
            }
            repair = prepare_refresh(col, settings).examples
            assert len(repair.updates) == 1
            assert not repair.updates[0].migration
            assert apply_example_refresh(col, repair).updated == 1
            repaired = col.get_note(production.id)
            assert repaired["UserExamples"] == damaged["UserExamples"]
            assert repaired.tags == damaged.tags
            for table in ("cards", "revlog"):
                assert col.db.all(f"select * from {table} order by id") == damaged_snapshot[table]
            col.undo()
            for table, expected in damaged_snapshot.items():
                assert col.db.all(f"select * from {table} order by id") == expected
            assert apply_example_refresh(col, repair, migrate=True).updated == 1
            assert not prepare_refresh(col, settings).examples.updates
            # Attribute-quote damage is also replaced automatically.
            import json

            automatic = col.get_note(production.id)
            raw = json.dumps(json.loads(automatic[STATE_FIELD]), ensure_ascii=False)
            for name, values in (
                ("data-source", ("vocabulary", "default", "components")),
                ("data-status", ("learned", "relearning", "learning", "new", "exists", "missing")),
            ):
                for value in values:
                    raw = raw.replace(
                        name + r"=\"" + value + r"\"", name + r'="\&quot;' + value + r'\&quot;"'
                    )
            automatic[STATE_FIELD] = raw
            col.update_note(automatic)
            automatic_before = dict(col.get_note(automatic.id).items())
            scheduling = {
                table: col.db.all(f"select * from {table} order by id")
                for table in ("cards", "revlog")
            }
            automatic_plan = prepare_refresh(col, settings).examples
            assert len(automatic_plan.updates) == 1
            assert not automatic_plan.updates[0].migration
            assert apply_example_refresh(col, automatic_plan).updated == 1
            assert {k: v for k, v in col.get_note(automatic.id).items() if k != STATE_FIELD} == {
                k: v for k, v in automatic_before.items() if k != STATE_FIELD
            }
            for table, expected in scheduling.items():
                assert col.db.all(f"select * from {table} order by id") == expected
            col.undo()
            assert dict(col.get_note(automatic.id).items()) == automatic_before
            assert apply_example_refresh(col, automatic_plan).updated == 1
            assert not prepare_refresh(col, settings).examples.updates
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
