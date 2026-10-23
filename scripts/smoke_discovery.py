"""Real-host Phase 1 checks. Fixture writes happen only in a disposable test profile."""

from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def seed_collection(collection):
    model = collection.models.by_name("Basic (and reversed card)")
    parent = collection.decks.id("Kanji Katanki smoke")
    child = collection.decks.id("Kanji Katanki smoke::Child")
    excluded = collection.decks.id("Excluded deck")
    for deck, front, back, note_type in (
        (parent, "景色", "秘密", model),
        (child, '<b>景</b>龘<img src="漢.svg">', "無視", model),
        (excluded, "漢字", "excluded deck", model),
        (parent, "別", "excluded note type", collection.models.by_name("Basic")),
    ):
        note = collection.new_note(note_type)
        note["Front"] = front
        note["Back"] = back
        note.tags = ["katanki_smoke_source"]
        collection.add_note(note, deck)
    return parent, child, model["id"]


def snapshot(collection):
    # Read-only SQL is confined to test verification, never the production adapter.
    return {
        table: collection.db.all(f"select * from {table} order by id")
        for table in ("notes", "cards", "revlog")
    }


def exercise_discovery(mw):

    from katanki.anki.analysis import analyze
    from katanki.common.models import ScanSelection

    parent, child, model_id = seed_collection(mw.col)
    before = snapshot(mw.col)
    selection = ScanSelection((parent, child), model_id, ("Front",))
    from scripts.smoke_settings import exercise_settings_dialog

    exercise_settings_dialog(mw, ScanSelection((parent,), model_id, ("Front",)))
    assert snapshot(mw.col) == before, "Settings changed notes/cards/review history"
    sources = {"kanjidic2": FIXTURES / "kanjidic2.xml", "kanjivg": FIXTURES / "kanjivg"}
    first = analyze(mw.col, selection, sources)
    second = analyze(mw.col, selection, sources)
    assert first == second, "Repeated scans returned different results"
    assert first.scan.scanned_notes == 2
    assert set(first.scan.candidates) == set("景色龘")
    assert {entry.character for entry in first.entries} == set("景色")
    assert first.unmatched == ("龘",)
    assert [entry.character for entry in first.strokes] == ["景"]
    assert snapshot(mw.col) == before, "Scan changed source fields/tags, cards, or review history"
    missing = analyze(mw.col, selection, {})
    assert not missing.dictionary_loaded and len(missing.unmatched) == 3
    assert snapshot(mw.col) == before
    bundled = analyze(mw.col, selection)
    assert {entry.character for entry in bundled.entries} == set("景色")
    assert {entry.character for entry in bundled.strokes} == set("景色")
    assert all("fixture" not in meaning for entry in bundled.entries for meaning in entry.meanings)
    assert snapshot(mw.col) == before
    return True
