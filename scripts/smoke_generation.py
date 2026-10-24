"""Phase 2 lifecycle check using a disposable real Anki collection, no personal data.

Run with the interpreter providing Anki: /usr/bin/python scripts/smoke_generation.py.
Read-only SQL below verifies exact snapshots; product code uses Anki APIs only.
"""

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main():
    from anki.collection import Collection
    from anki.scheduler.v3 import CardAnswer

    from katanki.anki.analysis import analyze
    from katanki.anki.generation import apply_generation, preview_generation
    from katanki.common.models import ScanSelection
    from katanki.generation.examples import STATE_FIELD, decode_state, managed_fields
    from katanki.generation.planner import Identity

    fixtures = ROOT / "tests/fixtures"
    sources = {"kanjidic2": fixtures / "kanjidic2.xml", "kanjivg": fixtures / "kanjivg"}
    with tempfile.TemporaryDirectory(prefix="katanki-generation-") as temporary:
        collection = Collection(str(Path(temporary) / "collection.anki2"))
        try:
            deck = collection.decks.id("Generated")
            source_deck = collection.decks.id("Vocabulary")
            model = collection.models.by_name("Basic")
            source = collection.new_note(model)
            source["Front"], source["Back"] = "景色", "scenery"
            collection.add_note(source, source_deck)
            selection = ScanSelection((source_deck,), model["id"], ("Front",))
            report = analyze(collection, selection, sources)

            def snapshot():
                return {
                    table: collection.db.all(f"select * from {table} order by id")
                    for table in ("notes", "cards", "revlog")
                }

            before = snapshot()
            choices = dict(recognition=("景", "色"), production=(), include_primitives=False)
            preview = preview_generation(collection, report, **choices)
            assert snapshot() == before, "Preview wrote to the collection"
            assert [item.outcome for item in preview.plan.items] == ["create", "create"]
            result = apply_generation(collection, preview, deck_id=deck)
            assert result.created == 2
            assert len(collection.find_cards(f"did:{deck}")) == 2
            # The exact already-approved plan is safe to apply again.
            assert apply_generation(collection, preview, deck_id=deck).created == 0
            rerun = preview_generation(collection, report, **choices)
            assert all(item.outcome == "skip" for item in rerun.plan.items)
            # Production can be selected for just 景, independently of recognition.
            production = preview_generation(
                collection,
                report,
                recognition=(),
                production=("景",),
                include_primitives=False,
            )
            production_content = production.contents[0]
            assert production_content.prompt == "fixture scenery\n\n__色"
            assert production_content.examples == ("景色",)
            assert apply_generation(collection, production, deck_id=deck).created == 1
            assert len(collection.find_cards(f"did:{deck}")) == 3
            production_nid = collection.find_notes('"note:Kanji Katanki — Kanji Production"')[0]
            front = collection.get_note(production_nid).cards()[0].question()
            assert "fixture scenery" in front and "__色" in front
            assert "景" not in front, "Production front reveals the target kanji"
            collection.undo()
            assert len(collection.find_cards(f"did:{deck}")) == 2
            assert apply_generation(collection, production, deck_id=deck).created == 1
            for nid in collection.find_notes(f"did:{deck}"):
                generated = collection.get_note(nid)
                assert len(generated.cards()) == 1
                assert generated.cards()[0].question()
                assert "katankiPlay" in generated.cards()[0].answer()
            assert analyze(collection, selection, sources).existing_owned == 2
            assert analyze(collection, selection, sources).missing_owned == 0
            collection.decks.select(deck)
            queued = collection.sched.get_queued_cards(fetch_limit=1).cards[0]
            card = collection.get_card(queued.card.id)
            card.start_timer()
            collection.sched.answer_card(
                collection.sched.build_answer(
                    card=card, states=queued.states, rating=CardAnswer.GOOD
                )
            )
            # Preserve user edits as well as actual scheduled state and review history.
            note = collection.get_note(card.nid)
            identity = Identity(note.note_type()["katanki_note_type"], note["Character"])
            managed = managed_fields(dict(note.items()), identity)
            assert decode_state(note[STATE_FIELD], managed) == managed
            assert "<" not in note[STATE_FIELD]
            note["Meanings"] = "My edited meaning"
            collection.update_note(note)
            assert collection.db.scalar("select count(*) from revlog") == 1
            generated_note_ids = set(collection.find_notes(f"did:{deck}"))
            collection.remove_notes([source.id])
            after_deletion = snapshot()
            empty_report = analyze(collection, selection, sources)
            assert empty_report.scan.candidates == ()
            empty_preview = preview_generation(
                collection,
                empty_report,
                recognition=(),
                production=(),
                include_primitives=False,
            )
            assert empty_preview.plan.items == ()
            # Rescan of the old snapshot also skips, preserving the same IDs and progress.
            again = preview_generation(collection, report, **choices)
            assert all(item.outcome == "skip" for item in again.plan.items)
            assert apply_generation(collection, preview, deck_id=deck).created == 0
            assert snapshot() == after_deletion, "Generated notes/cards/revlog changed on rerun"
            assert set(collection.find_notes(f"did:{deck}")) == generated_note_ids
            assert all(len(collection.get_note(nid).cards()) == 1 for nid in generated_note_ids)
            # User formatting must not conceal a production-prompt collision.
            production_id = collection.find_notes('"note:Kanji Katanki — Kanji Production"')[0]
            production_note = collection.get_note(production_id)
            production_note["Prompt"] = "<b>fixture color</b><br><br>景__"
            collection.update_note(production_note)
            before_collision = snapshot()
            try:
                preview_generation(
                    collection,
                    report,
                    recognition=(),
                    production=("色",),
                    include_primitives=False,
                )
            except ValueError as error:
                assert "already belongs" in str(error)
            else:
                raise AssertionError("Existing production prompt collision was accepted")
            assert snapshot() == before_collision
            # A failed batch retains its partial creations for safe resume/Undo.
            components = preview_generation(
                collection,
                report,
                recognition=("景",),
                production=(),
                include_primitives=True,
            )
            original_add = collection.add_note
            attempts = 0

            def fail_second(note, deck_id):
                nonlocal attempts
                attempts += 1
                if attempts == 2:
                    raise RuntimeError("Injected write failure")
                return original_add(note, deck_id)

            collection.add_note = fail_second
            try:
                try:
                    apply_generation(collection, components, deck_id=deck)
                except RuntimeError as error:
                    assert "creating 1 notes" in str(error)
                else:
                    raise AssertionError("Injected batch failure was ignored")
            finally:
                collection.add_note = original_add
            assert apply_generation(collection, components, deck_id=deck).created == 1
            collection.undo()  # Undo resumed creation.
            collection.undo()  # Undo initial partial creation and its model.
            assert snapshot() == before_collision
            print("PASS: preview is read-only; generation is idempotent; production is selective;")
            print(
                "source deletion preserves generated note/card IDs, edits, scheduling and revlog."
            )
        finally:
            collection.close()


def exercise_stroke_controls(mw):
    """Execute generated card JavaScript in the real Anki webview, offline."""
    from aqt.qt import QEventLoop, QTimer
    from aqt.webview import AnkiWebView

    from katanki.anki.identities import owned_identities

    identity_notes = owned_identities(mw.col, note_type="kanji-recognition")
    nid = next(ids[0] for identity, ids in identity_notes.items() if identity.key == "景")
    card = mw.col.get_note(nid).cards()[0]
    web = AnkiWebView(parent=mw)
    loop = QEventLoop()
    timer = QTimer(mw)
    timer.setInterval(50)
    results = []
    pending = False
    javascript = """(function() {
      if (typeof katankiNumbers !== 'function' || typeof katankiPlay !== 'function') return null;
      var buttons = Array.from(document.querySelectorAll('button'));
      var numbers = buttons.find(function(b) { return b.textContent === 'Stroke numbers'; });
      var play = buttons.find(function(b) { return b.textContent === 'Play strokes'; });
      if (!numbers || !play) return null;
      var paths = document.querySelectorAll('.strokes svg path').length;
      katankiNumbers(numbers);
      var count = document.querySelectorAll('.katanki-number').length;
      katankiNumbers(numbers);
      var cleared = document.querySelectorAll('.katanki-number').length === 0;
      katankiPlay(play);
      var animations = document.getAnimations().length;
      return {paths: paths, numbers: count, cleared: cleared, animations: animations};
    })()"""

    def checked(result):
        nonlocal pending
        pending = False
        if result:
            results.append(result)
            loop.quit()

    def poll():
        nonlocal pending
        if not pending:
            pending = True
            web.evalWithCallback(javascript, checked)

    timer.timeout.connect(poll)
    web.stdHtml(card.answer())
    timer.start()
    QTimer.singleShot(10_000, loop.quit)
    try:
        loop.exec()
    finally:
        timer.stop()
        web.cleanup()
        web.deleteLater()
    assert results, "Generated card stroke controls did not load in the webview"
    result = results[0]
    assert result["paths"] > 0
    assert result["numbers"] == result["paths"]
    assert result["cleared"]
    assert result["animations"] == result["paths"]


if __name__ == "__main__":
    main()
