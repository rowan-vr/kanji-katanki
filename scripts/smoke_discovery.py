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


def exercise_dialog(mw, action):
    from aqt.qt import Qt, QTimer

    from katanki.anki.analysis import analyze
    from katanki.common.models import ScanSelection
    from katanki.ui.discovery import DiscoveryDialog

    parent, child, model_id = seed_collection(mw.col)
    before = snapshot(mw.col)
    selection = ScanSelection((parent, child), model_id, ("Front",))
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
    errors = []
    completed = False
    started = False
    phase = "fixtures"
    timer = QTimer(mw)
    timer.setInterval(50)

    def drive():
        nonlocal started, completed, phase
        dialog = next(
            (widget for widget in mw.app.topLevelWidgets() if isinstance(widget, DiscoveryDialog)),
            None,
        )
        if dialog is None:
            return
        try:
            if not started:
                started = True
                for index in range(dialog.decks.count()):
                    item = dialog.decks.item(index)
                    item.setSelected(item.data(Qt.ItemDataRole.UserRole) == parent)
                dialog.types.setCurrentIndex(
                    next(
                        index
                        for index, model in enumerate(dialog.note_types)
                        if model[0] == model_id
                    )
                )
                for index in range(dialog.fields.count()):
                    item = dialog.fields.item(index)
                    item.setSelected(item.text() == "Front")
                for dataset_id, path in sources.items():
                    dialog.sources[dataset_id].setText(str(path))
                dialog._scan()
            elif dialog.report is not None and not dialog.busy:
                assert not dialog.preview.pixmap().isNull(), "SVG preview did not render"
                assert "SHA-256" in dialog.provenance.toPlainText()
                if phase == "fixtures":
                    assert dialog.report == first
                    assert "Scanned notes: 2" in dialog.summary.text()
                    assert "fixture scenery" in dialog.detail.toPlainText()
                    for entry in dialog.sources.values():
                        entry.clear()
                    phase = "bundled"
                    dialog._scan()
                else:
                    assert dialog.report == bundled
                    assert "fixture scenery" not in dialog.detail.toPlainText()
                    completed = True
                    timer.stop()
                    dialog.reject()
            elif not dialog.busy:
                raise AssertionError(dialog.summary.text())
        except Exception as error:
            errors.append(error)
            timer.stop()
            dialog.reject()

    timer.timeout.connect(drive)
    timer.start()
    action.trigger()
    timer.stop()
    if errors:
        raise errors[0]
    assert completed, "Discovery dialog check did not finish"
    assert snapshot(mw.col) == before, "UI scan changed collection data"
    return True
