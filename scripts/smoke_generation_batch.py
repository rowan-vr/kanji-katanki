"""Regression for batches larger than Anki's bounded Undo history.

Run with /usr/bin/python scripts/smoke_generation_batch.py; uses temporary data only.
"""

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main():
    from anki.collection import Collection

    from katanki.anki.generation import apply_generation
    from katanki.generation.cards import CardContent
    from katanki.generation.planner import Identity, LearningUnit, plan_generation
    from katanki.generation.preview import GenerationPreview

    units, contents = [], []
    for number in range(650):
        character = chr(0x4E00 + number)
        for mode in ("recognition", "production"):
            identity = Identity(f"kanji-{mode}", character)
            units.append(LearningUnit(identity))
            contents.append(CardContent(identity, character, prompt=f"Synthetic clue {number}"))
    preview = GenerationPreview(
        plan_generation(units, (), include_primitives=False), tuple(contents), ()
    )
    with tempfile.TemporaryDirectory(prefix="katanki-batch-") as temporary:
        collection = Collection(str(Path(temporary) / "collection.anki2"))
        try:
            deck = collection.decks.id("Generated")
            result = apply_generation(collection, preview, deck_id=deck)
            assert result.created == 1300
            assert collection.note_count() == 1300
            assert len(collection.find_cards("")) == 1300
            assert apply_generation(collection, preview, deck_id=deck).created == 0
            collection.undo()
            assert collection.note_count() == 0, "One Undo must remove the entire batch"
            # A failure after hundreds of successful notes must still group and resume.
            original_add = collection.add_note
            calls = 0

            def fail_after_400(note, deck_id):
                nonlocal calls
                calls += 1
                if calls == 401:
                    raise RuntimeError("Injected large-batch failure")
                return original_add(note, deck_id)

            collection.add_note = fail_after_400
            try:
                try:
                    apply_generation(collection, preview, deck_id=deck)
                except RuntimeError as error:
                    assert "creating 400 notes" in str(error)
                    assert "Injected large-batch failure" in str(error.__cause__)
                else:
                    raise AssertionError("Injected failure was ignored")
            finally:
                collection.add_note = original_add
            assert collection.note_count() == 400
            assert apply_generation(collection, preview, deck_id=deck).created == 900
            assert collection.note_count() == 1300
            collection.undo()
            assert collection.note_count() == 400
            collection.undo()
            assert collection.note_count() == 0
            print("PASS: 1300-note generation, single Undo, rerun, partial failure and resume.")
        finally:
            collection.close()


if __name__ == "__main__":
    main()
