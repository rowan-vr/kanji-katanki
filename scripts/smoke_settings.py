"""Verify settings persistence and Qt controls using disposable Anki data."""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]


def exercise_settings_dialog(mw, selection):
    from katanki.config import Settings, SourceRule, load_settings
    from katanki.ui.discovery import DiscoveryDialog
    from katanki.ui.settings import SettingsDialog

    original = load_settings(mw.col)
    cancelled = SettingsDialog(mw)
    cancelled.primitives.setChecked(not original.include_primitives)
    cancelled.reject()
    assert load_settings(mw.col) == original, "Cancel saved settings"

    dialog = SettingsDialog(mw)
    rules = (
        SourceRule("*", selection.note_type_id, selection.fields),
        SourceRule("", selection.note_type_id, selection.fields, selection.deck_ids),
    )
    dialog.sources.restore(rules)
    assert dialog.tabs.tabText(0) == "Discovery"
    dialog.deck.setCurrentIndex(dialog.deck.findData(selection.deck_ids[0]))
    dialog.primitives.setChecked(True)
    dialog._save()
    expected = Settings(rules, selection.deck_ids[0], True)
    assert load_settings(mw.col) == expected
    reopened = SettingsDialog(mw)
    assert reopened.sources.rules() == rules
    assert reopened.deck.currentData() == expected.destination_deck_id
    assert reopened.primitives.isChecked()
    reopened.reject()
    discovery = DiscoveryDialog(mw)
    assert discovery.source_selector.rules() == rules
    discovery.reject()
    # Exercise adding/removing and editing rows, then restore the fixture scan defaults.
    row = reopened.sources.add_rule(
        SourceRule("Japanese::*", selection.note_type_id, selection.fields)
    )
    assert reopened.sources.rules()[-1].deck_pattern == "Japanese::*"
    reopened.sources.remove_rule(row)
    assert reopened.sources.rules() == rules
    dialog = SettingsDialog(mw)
    dialog.sources.restore(
        (SourceRule("", selection.note_type_id, selection.fields, selection.deck_ids),)
    )
    from aqt.qt import QDialog, QEventLoop, QTimer

    from scripts.smoke_discovery import snapshot

    saved_before = load_settings(mw.col)
    notes_before = snapshot(mw.col)
    loop = QEventLoop()
    timer = QTimer(mw)
    errors = []
    completed = False

    def close_results():
        nonlocal completed
        result_dialog = next(
            (
                widget
                for widget in mw.app.topLevelWidgets()
                if isinstance(widget, QDialog)
                and widget.objectName() == "katanki_discovery_test_results"
                and widget.isVisible()
            ),
            None,
        )
        if result_dialog:
            try:
                assert dialog.test_result.scanned_notes == 2
                assert set(dialog.test_result.candidates) == set("景色龘")
                assert not dialog.busy
                completed = True
            except Exception as error:
                errors.append(error)
            result_dialog.reject()
            loop.quit()

    timer.timeout.connect(close_results)
    timer.start(25)
    deadline = QTimer(mw)
    deadline.setSingleShot(True)
    deadline.timeout.connect(loop.quit)
    deadline.start(10_000)
    dialog._test_discovery()
    loop.exec()
    timer.stop()
    deadline.stop()
    if errors:
        raise errors[0]
    assert completed, "Settings discovery test did not show its results"
    assert load_settings(mw.col) == saved_before, "Testing saved unsaved source settings"
    assert snapshot(mw.col) == notes_before, "Discovery test changed notes/cards/review history"
    dialog._save()
    print("PASS: Settings Save/Cancel, unsaved discovery test, reopening, and source defaults")


def main():
    sys.path.insert(0, str(ROOT / "src"))
    from anki.collection import Collection

    from katanki.anki.collection import resolve_sources, selected_notes
    from katanki.config import Settings, SourceRule, load_settings, save_settings
    from katanki.generation.discovery import scan_notes

    with TemporaryDirectory(prefix="katanki-settings-") as directory:
        path = str(Path(directory) / "collection.anki2")
        collection = Collection(path)
        try:
            source = collection.decks.id("Vocabulary")
            model_id = collection.models.by_name("Basic")["id"]
            other_model = collection.models.by_name("Basic (and reversed card)")
            for model, front, back in (
                (collection.models.by_name("Basic"), "景", "色"),
                (other_model, "時間", "秘密"),
            ):
                note = collection.new_note(model)
                note["Front"], note["Back"] = front, back
                collection.add_note(note, source)
            rules = (
                SourceRule("*", model_id, ("Front",)),
                SourceRule("", other_model["id"], ("Front",), (source,)),
                SourceRule("Vocabulary*", model_id, ("Back",)),
            )
            scan = scan_notes(selected_notes(collection, resolve_sources(collection, rules)))
            assert scan.scanned_notes == 2
            assert set(scan.candidates) == set("景色時間")
            assert "秘密" not in scan.vocabulary
            expected = Settings(rules, source, True)
            save_settings(collection, expected)
        finally:
            collection.close()
        reopened = Collection(path)
        try:
            assert load_settings(reopened) == expected
        finally:
            reopened.close()
    print(
        "PASS: mixed note types/fields, overlapping wildcards, and persisted settings in real Anki"
    )


if __name__ == "__main__":
    main()
