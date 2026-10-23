"""Verify settings persistence and Qt controls using disposable Anki data."""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]


def exercise_settings_dialog(mw, selection):
    from katanki.config import Settings, SourceRule, load_settings
    from katanki.ui.settings import SettingsDialog

    original = load_settings(mw.col)
    cancelled = SettingsDialog(mw)
    cancelled.primitives.setChecked(not original.include_primitives)
    cancelled.card_panels["recognition"].refresh.setChecked(False)
    cancelled.card_panels["recognition"].limit.setValue(0)
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
    assert [dialog.generation_tabs.tabText(i) for i in range(3)] == [
        "Recognition",
        "Production",
        "Parts",
    ]
    for category, panel in dialog.generation_panels.items():
        panel.tags.setText("katanki " + category)
        panel.copy_tags.setChecked(True)
        panel.patterns.setText("source::NIJ::*")
    assert [dialog.tabs.tabText(i) for i in range(dialog.tabs.count())] == [
        "Discovery",
        "Generation",
        "Cards",
        "Dictionaries",
        "Ignored cards",
    ]
    assert [dialog.card_tabs.tabText(i) for i in range(3)] == ["Recognition", "Production", "Parts"]
    for index, panel in enumerate(dialog.card_panels.values()):
        assert panel.refresh.isChecked()
        assert panel.limit.value() == 5
        panel.limit.setValue((0, 3, 10)[index])
        panel.examples.setChecked(index != 0)
        panel.source.setCurrentIndex(index % 2)
        if panel.category == "parts":
            assert not hasattr(panel, "furigana")
            assert not hasattr(panel, "word_status")
            assert panel.examples.text() == "Show example kanji containing the part on the back"
            panel.name.setChecked(False)
        else:
            assert panel.source.itemText(0) == "Your vocabulary words only"
            panel.furigana.setChecked(index == 1)
            panel.word_status.setCurrentIndex(index % 2)
        panel.refresh.setChecked(index != 1)
    dialog._save()
    expected = Settings(
        rules,
        selection.deck_ids[0],
        True,
        tuple(panel.settings() for panel in dialog.generation_panels.values()),
        dialog.dictionary_panel.choices(),
        tuple(panel.settings() for panel in dialog.card_panels.values()),
    )
    assert load_settings(mw.col) == expected
    reopened = SettingsDialog(mw)
    assert reopened.sources.rules() == rules
    assert reopened.deck.currentData() == expected.destination_deck_id
    assert reopened.primitives.isChecked()
    for category, panel in reopened.generation_panels.items():
        assert panel.settings() == expected.generation_settings(category)
    for category, panel in reopened.card_panels.items():
        assert panel.settings() == expected.card_settings(category)
    reopened.reject()
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
    exercise_dictionary_settings(mw, selection)
    print("PASS: Settings Save/Cancel, unsaved discovery test, reopening, and source defaults")


def exercise_dictionary_settings(mw, selection):
    from dataclasses import replace

    from aqt.qt import QEventLoop, QTimer

    from katanki.anki.analysis import analyze
    from katanki.config import DictionaryChoice, load_settings, save_settings
    from katanki.ui.settings import SettingsDialog
    from scripts.smoke_discovery import snapshot

    original = load_settings(mw.col)
    before = snapshot(mw.col)
    dialog = SettingsDialog(mw)
    assert dialog.tabs.tabText(3) == "Dictionaries"
    panels = dialog.dictionary_panel.panels
    kanji = panels["kanjidic2"]
    assert "EDRDG" in kanji.about.toPlainText()
    assert "SHA-256" in kanji.about.toPlainText()
    assert kanji.notice.toPlainText()
    kanji.mode.setCurrentIndex(kanji.mode.findData("local"))
    kanji.path.setText(str(ROOT / "tests/fixtures/kanjidic2.xml"))
    strokes = panels["kanjivg"]
    strokes.mode.setCurrentIndex(strokes.mode.findData("disabled"))
    assert load_settings(mw.col) == original
    loop = QEventLoop()
    poll = QTimer(mw)
    poll.timeout.connect(lambda: loop.quit() if not dialog.busy else None)
    deadline = QTimer(mw)
    deadline.setSingleShot(True)
    deadline.timeout.connect(loop.quit)
    poll.start(25)
    deadline.start(10_000)
    kanji._check()
    loop.exec()
    poll.stop()
    deadline.stop()
    assert not dialog.busy and kanji.status.text() == "Check passed"
    assert "SHA-256" in kanji.check_details.toPlainText()
    assert load_settings(mw.col) == original, "Dictionary check saved settings"
    dialog._save()
    expected = dialog.dictionary_panel.choices()
    reopened = SettingsDialog(mw)
    assert reopened.dictionary_panel.choices() == expected
    reopened.reject()
    report = analyze(mw.col, selection)
    assert report.dictionary_loaded and report.entries and not report.strokes
    save_settings(
        mw.col,
        replace(
            original,
            dictionaries=(
                DictionaryChoice("kanjidic2", "disabled"),
                DictionaryChoice("kanjivg", "disabled"),
            ),
        ),
    )
    assert not analyze(mw.col, selection).dictionary_loaded
    save_settings(mw.col, original)
    assert snapshot(mw.col) == before, "Dictionary settings/checks changed collection data"
    print(
        "PASS: dictionary attribution, local check, saved choices, disabled sources, and no writes"
    )
    exercise_dictionary_updates(mw)


def exercise_dictionary_updates(mw):
    """Use synthetic packs to exercise actual asynchronous Qt update controls."""
    import json
    from unittest.mock import patch

    from aqt.qt import QEventLoop, QMessageBox, QTimer

    from katanki.dictionaries import updates
    from katanki.ui.settings import SettingsDialog

    sys.path.insert(0, str(ROOT / "tests"))
    from dataset_pack_helpers import candidate

    manifest, release, payload = candidate()
    catalog = json.dumps({"schema_version": 1, "datasets": {manifest.id: release}}).encode()

    def wait(dialog, action, *, update=False):
        loop = QEventLoop()
        poll, deadline = QTimer(mw), QTimer(mw)
        messages = []

        def respond():
            for popup in dialog.findChildren(QMessageBox):
                if popup.isVisible() and popup.objectName() == "katanki_dictionary_update_result":
                    messages.append(popup.text())
                    button = next(
                        (
                            button
                            for button in popup.buttons()
                            if update and button.text() == "Update"
                        ),
                        popup.button(QMessageBox.StandardButton.Close),
                    )
                    button.click()
                    return
            if not dialog.busy:
                loop.quit()

        poll.timeout.connect(respond)
        deadline.setSingleShot(True)
        deadline.timeout.connect(loop.quit)
        action()
        poll.start(25)
        deadline.start(10_000)
        loop.exec()
        poll.stop()
        deadline.stop()
        assert not dialog.busy, "Dictionary operation did not finish"
        return messages

    with TemporaryDirectory(prefix="katanki-update-smoke-") as directory:
        with (
            patch.object(updates, "USER_DATA", Path(directory)),
            patch.object(
                updates,
                "download",
                side_effect=lambda url, **_: catalog if url == updates.CATALOG_URL else payload,
            ) as network,
        ):
            dialog = SettingsDialog(mw)
            panel = dialog.dictionary_panel
            kanji = panel.panels[manifest.id]
            messages = wait(dialog, panel._check_updates)
            assert any("Dictionary updates are available" in text for text in messages)
            assert "Last successful check" in panel.update_status.text()
            assert "Check complete: updates available for KANJIDIC2." in panel.update_status.text()
            assert kanji.update_button.isEnabled()
            messages = wait(dialog, panel._check_updates, update=True)
            assert any("KANJIDIC2: updated to" in text for text in messages)
            assert "Downloaded version" in kanji.update_status.text()
            assert "fixture attribution" in kanji.notice.toPlainText()
            messages = wait(dialog, panel._check_updates)
            assert "All dictionaries are up to date." in messages
            assert "Check complete: no dictionary updates available." in panel.update_status.text()
            kanji.mode.setCurrentIndex(kanji.mode.findData("local"))
            assert not kanji.update_button.isEnabled() and not kanji.bundled_button.isEnabled()
            kanji.mode.setCurrentIndex(kanji.mode.findData("bundled"))
            kanji.bundled_button.click()
            assert "Bundled version" in kanji.update_status.text()
            network.side_effect = OSError("offline")
            messages = wait(dialog, panel._check_updates)
            assert any("Update check failed:" in text and "offline" in text for text in messages)
            assert "Update check failed" in panel.update_status.text()
            panel.automatic.setChecked(True)
            dialog.reject()
            assert not updates.preferences().get("automatic", False), (
                "Cancel saved update preferences"
            )
    print(
        "PASS: async dictionary checks, validated install, notices, fallback, and offline failure"
    )


def exercise_category_generation(collection, rules):
    from dataclasses import replace

    from katanki.anki.analysis import analyze
    from katanki.anki.collection import resolve_sources
    from katanki.anki.generation import apply_generation, preview_generation
    from katanki.config import GenerationSettings, Settings

    decks = [
        collection.decks.id("Generated::" + name) for name in ("Recognition", "Production", "Parts")
    ]
    preferences = Settings(
        generation=(
            GenerationSettings(True, decks[0], ("recognition",), True, ("source::NIJ::*",)),
            GenerationSettings(True, decks[1], ("production",), True),
            GenerationSettings(True, decks[2], ("parts",), True, ("source::NIJ::*",)),
        )
    )
    fixtures = ROOT / "tests/fixtures"
    report = analyze(
        collection,
        resolve_sources(collection, rules),
        {"kanjidic2": fixtures / "kanjidic2.xml", "kanjivg": fixtures / "kanjivg"},
    )
    choices = dict(
        recognition=("景",),
        production=("景",),
        primitive_recognition=("日",),
        include_primitives=False,
        generation_settings=preferences,
    )
    preview = preview_generation(collection, report, **choices)
    assert len(preview.creations) == 3
    before = collection.note_count()
    invalid = replace(
        preview,
        creations=(replace(preview.creations[0], deck_id=999999999), *preview.creations[1:]),
    )
    try:
        apply_generation(collection, invalid)
    except ValueError:
        pass
    else:
        raise AssertionError("Missing destination did not reject the whole plan")
    assert collection.note_count() == before
    result = apply_generation(collection, preview)
    assert result.created == 3
    for options in preview.creations:
        ids = collection.find_notes(f"did:{options.deck_id}")
        assert len(ids) == 1
        assert set(collection.get_note(ids[0]).tags) == set(options.tags)
        category = (
            "parts"
            if options.identity.kind == "primitive"
            else options.identity.note_type.split("-")[1]
        )
        assert category in options.tags
        assert "source::NIJ::lesson1" in options.tags
        assert ("unrelated" in options.tags) == (category == "production")
    assert apply_generation(collection, preview).created == 0
    assert all(
        item.outcome == "skip"
        for item in preview_generation(collection, report, **choices).plan.items
    )
    print("PASS: category decks, copied tags, atomic validation, and reruns")


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
                note.tags = ["source::NIJ::lesson1", "source::Other::lesson2", "unrelated"]
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
            exercise_category_generation(collection, rules)
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
