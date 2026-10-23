"""Exercise single-window review, previews, persistent ignores, and no-op refreshes."""


def exercise_refresh(mw, action):
    import os
    from dataclasses import replace
    from pathlib import Path

    from aqt.qt import QEventLoop, QTimer

    from katanki.anki.identities import owned_identities
    from katanki.anki.ignored import load_ignored
    from katanki.config import DictionaryChoice, GenerationSettings, load_settings, save_settings
    from katanki.generation.planner import Identity
    from katanki.ui import generation, refresh
    from katanki.ui.settings import SettingsDialog
    from scripts.smoke_discovery import snapshot

    settings = load_settings(mw.col)
    source = settings.sources[0]
    note = mw.col.new_note(mw.col.models.get(source.note_type_id))
    note[source.fields[0]] = "時"
    note.tags = ["source::NIJ::refresh", "unrelated"]
    mw.col.add_note(note, source.deck_ids[0])
    decks = [mw.col.decks.id("Refresh::" + category) for category in ("Recognition", "Production")]
    settings = replace(
        settings,
        generation=(
            GenerationSettings(True, decks[0], ("recognition",), True, ("source::NIJ::*",)),
            GenerationSettings(True, decks[1], ("production",), True, ("source::NIJ::*",)),
            GenerationSettings(False),
        ),
    )
    save_settings(mw.col, settings)
    messages, errors = [], []
    original = generation.tooltip, generation.showWarning, refresh.tooltip, refresh.showWarning
    generation.tooltip = refresh.tooltip = lambda message, **_: messages.append(message)
    generation.showWarning = refresh.showWarning = lambda message, **_: errors.append(
        AssertionError(message)
    )
    ignored_identity = Identity("kanji-production", "時")

    def run(mode, expected_tabs=None):
        loop = QEventLoop()
        timer, deadline = QTimer(mw), QTimer(mw)
        deadline.setSingleShot(True)
        deadline.timeout.connect(loop.quit)
        reviewed = False
        count = 0

        def drive():
            nonlocal reviewed, count
            dialogs = [
                widget
                for widget in mw.app.topLevelWidgets()
                if isinstance(widget, generation.CreationReviewDialog) and widget.isVisible()
            ]
            try:
                if errors:
                    raise errors[0]
                assert len(dialogs) <= 1, "Refresh opened duplicate review windows"
                if dialogs and not reviewed:
                    reviewed = True
                    dialog = dialogs[0]
                    if expected_tabs is not None:
                        assert list(dialog.tiles) == expected_tabs
                    assert all(
                        item.background().color().name() == "#286442"
                        for item in dialog.items.values()
                    )
                    count = len(dialog.preview.creations)
                    if mode == "choose_targets":
                        assert not dialog.create_button.isEnabled()
                        for category, combo in dialog.decks.items():
                            combo.setCurrentIndex(
                                combo.findData(decks[0 if category == "recognition" else 1])
                            )
                    assert count and dialog.create_button.isEnabled()
                    tile = next(iter(dialog.items.values()))
                    dialog._show_card(tile)
                    assert dialog.card_details.text().startswith(tile.text())
                    screenshot = os.environ.get("KATANKI_REVIEW_SCREENSHOT")
                    if screenshot and not Path(screenshot).exists():
                        render_loop = QEventLoop()
                        QTimer.singleShot(350, render_loop.quit)
                        render_loop.exec()
                        dialog.grab().save(screenshot)
                    if mode == "ignore":
                        tile = dialog.items[ignored_identity]
                        view = dialog.tiles["production"]
                        dialog.tabs.setCurrentIndex(1)
                        view.scrollToItem(tile)
                        dialog._right_click(view, view.visualItemRect(tile).center())
                        assert ignored_identity in load_ignored(mw.col)
                        assert tile.background().color().name() == "#454b55"
                        assert Identity("kanji-recognition", "時") not in load_ignored(mw.col)
                        dialog.reject()
                    elif mode in ("create", "choose_targets"):
                        dialog.create_button.click()
                    else:
                        dialog.reject()
                elif not getattr(mw, "_katanki_refresh_running", False):
                    timer.stop()
                    loop.quit()
            except Exception as error:
                errors.append(error)
                timer.stop()
                if dialogs and not dialogs[0].busy:
                    dialogs[0].reject()
                loop.quit()

        timer.timeout.connect(drive)
        timer.start(25)
        deadline.start(15_000)
        action.trigger()
        assert mw._katanki_refresh_running
        action.trigger()
        loop.exec()
        timer.stop()
        deadline.stop()
        if errors:
            raise errors[0]
        assert not mw._katanki_refresh_running, "Refresh did not finish"
        if mode == "noop":
            assert not reviewed, "Up-to-date/ignored cards prompted for creation"
        else:
            assert reviewed
        return count

    try:
        before = snapshot(mw.col)
        initial_count = mw.col.note_count()
        pending = run("cancel", ["recognition", "production"])
        assert snapshot(mw.col) == before
        run("ignore", ["recognition", "production"])
        assert snapshot(mw.col) == before, "Ignore mutated cards instead of preferences"
        creating = run("create", ["recognition", "production"])
        assert creating == pending - 1
        assert mw.col.note_count() == initial_count + creating
        assert all(
            identity.key != "時"
            for identity in owned_identities(mw.col, note_type="kanji-production")
        )
        after = snapshot(mw.col)
        run("noop")
        assert snapshot(mw.col) == after
        settings_dialog = SettingsDialog(mw)
        ignored_panel = settings_dialog.ignored_panel
        assert ignored_panel.cards.count() == 1
        ignored_panel.cards.item(0).setSelected(True)
        ignored_panel._restore()
        settings_dialog.reject()
        assert not load_ignored(mw.col)
        assert run("create", ["production"]) == 1
        for note_type, deck_id in zip(
            ("kanji-recognition", "kanji-production"), decks, strict=True
        ):
            identity_notes = owned_identities(mw.col, note_type=note_type)
            note_id = next(
                ids[0] for identity, ids in identity_notes.items() if identity.key == "時"
            )
            generated = mw.col.get_note(note_id)
            assert set(generated.tags) == {note_type.split("-")[1], "source::NIJ::refresh"}
            assert all(card.did == deck_id for card in generated.cards())
        after = snapshot(mw.col)
        run("noop")
        assert snapshot(mw.col) == after
        parts_deck = mw.col.decks.id("Refresh::Parts")
        fixtures = Path(__file__).resolve().parents[1] / "tests/fixtures"
        parts_settings = replace(
            settings,
            generation=(
                GenerationSettings(False),
                GenerationSettings(False),
                GenerationSettings(True, parts_deck),
            ),
            dictionaries=(
                DictionaryChoice("kanjidic2", "local", str(fixtures / "kanjidic2.xml")),
                DictionaryChoice("kanjivg", "local", str(fixtures / "kanjivg")),
            ),
        )
        save_settings(mw.col, parts_settings)
        assert run("create", ["parts"]) == 2
        run("noop")
        note = mw.col.new_note(mw.col.models.get(source.note_type_id))
        note[source.fields[0]] = "間"
        mw.col.add_note(note, source.deck_ids[0])
        save_settings(
            mw.col,
            replace(
                settings,
                generation=(
                    GenerationSettings(True),
                    GenerationSettings(False),
                    GenerationSettings(False),
                ),
            ),
        )
        assert run("choose_targets", ["recognition"]) == 1
        assert all(
            identity.key != "間"
            for identity in owned_identities(mw.col, note_type="kanji-production")
        )
        run("noop")
        assert messages
    finally:
        generation.tooltip, generation.showWarning, refresh.tooltip, refresh.showWarning = original
    print("PASS: single review, tiles/preview, ignore/restore, creation, and quiet reruns")
