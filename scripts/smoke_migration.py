"""Verify migration history, scheduling, Undo, rollback and Qt against real Anki."""

import sys
from dataclasses import replace
from pathlib import Path
from shutil import copytree
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main():
    import anki
    from anki import cards_pb2
    from anki.collection import Collection
    from aqt.qt import QApplication, QWidget

    from katanki.anki.identities import MODEL_MARKER
    from katanki.anki.migration import (
        MigrationSource,
        _schedule,
        apply_migration,
        prepare_migration,
    )
    from katanki.config import DictionaryChoice, Settings, save_settings
    from katanki.ui.migration import MigrationDialog

    app = QApplication.instance() or QApplication([])
    with TemporaryDirectory(prefix="katanki-migration-") as directory:
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
                    DictionaryChoice("jitendex", "disabled"),
                ),
            )
            save_settings(col, settings)
            model = col.models.by_name("Basic (and reversed card)")
            col.models.add_field(model, col.models.new_field("Meaning"))
            col.models.update_dict(model)
            source = col.new_note(model)
            source["Front"], source["Back"] = "<b>景</b>", "Keep my mnemonic [sound:old.mp3]"
            source.tags = ["old", "user::tag"]
            col.add_note(source, 1)
            production_deck = col.decks.id("Writing source")
            ids = tuple(card.id for card in source.cards())
            for index, cid in enumerate(ids):
                card = col.get_card(cid)
                if index == 1:
                    card.did = production_deck
                card.type, card.queue = (2, -1) if index == 0 else (3, 1)
                card.ivl, card.due, card.factor = 51, 120, 2450
                card.reps, card.lapses, card.left, card.flags = 20, 3, 1001, 3
                card.memory_state = cards_pb2.FsrsMemoryState(stability=42.5, difficulty=4.2)
                card.desired_retention = 0.9
                card.last_review_time = 1700000000
                card.custom_data = '{"mt":1}'
                col.update_card(card)
                # Historical fixture only; migration itself never writes SQL.
                col.db.execute(
                    "insert into revlog values (?, ?, 0, 3, 51, 30, 2450, 1200, 1)",
                    1700000000000 + index,
                    cid,
                )
            rules = tuple(
                MigrationSource(mode, 1 if index == 0 else production_deck, model["id"], "Front")
                for index, mode in enumerate(("recognition", "production"))
            )
            before = {
                t: col.db.all(f"select * from {t} order by id")
                for t in ("notes", "cards", "revlog")
            }
            schedules = {cid: _schedule(col.get_card(cid)) for cid in ids}
            events = []

            def progress(message, current, total):
                events.append((message, current, total))

            plan = prepare_migration(col, rules, progress=progress)
            assert any("Loading dictionaries" in message for message, _, _ in events)
            assert any(
                "Reading history" in message and current == total == 2
                for message, current, total in events
            )
            assert len(plan.items) == 2, plan.warnings
            assert all(col.db.all(f"select * from {t} order by id") == before[t] for t in before)
            dialog = MigrationDialog(mw)
            dialog.loaded(plan)
            assert dialog.apply_button.isEnabled()
            assert dialog.review.item(0, 5).text() == "1"
            assert set(dialog.mappings) == {"recognition", "production"}
            dialog.mappings["recognition"].deck.setCurrentIndex(1)
            assert dialog.plan is None and not dialog.apply_button.isEnabled()
            dialog.show()
            app.processEvents()
            assert not dialog.grab().isNull()
            dialog.reject()
            assert all(col.db.all(f"select * from {t} order by id") == before[t] for t in before)
            backups = Path(directory) / "backups"
            backups.mkdir()
            col.create_backup(backup_folder=str(backups), force=True, wait_for_completion=True)
            assert list(backups.glob("*.colpkg"))
            events.clear()
            apply_migration(col, plan, progress=progress)
            assert any(
                "Converting" in message and current == total == 2
                for message, current, total in events
            )
            assert any(
                "Verifying preserved" in message and current == total == 2
                for message, current, total in events
            )
            assert set(col.find_cards("")) == set(ids)
            assert col.db.all("select * from revlog order by id") == before["revlog"]
            for cid in ids:
                card = col.get_card(cid)
                assert _schedule(card) == schedules[cid]
                note = col.get_note(card.nid)
                assert note.note_type()[MODEL_MARKER].startswith("kanji-")
                assert set(note.tags) == set(source.tags)
                assert "MigrationSource" not in note.keys()
            assert not prepare_migration(col, rules).items
            # Existing migration archive fields are removed under the same Undo entry.
            fixture_undo = col.add_custom_undo_entry("legacy archive fixture")
            migrated = col.get_note(col.get_card(ids[0]).nid)
            target_model = migrated.note_type()
            col.models.add_field(target_model, col.models.new_field("MigrationSource"))
            col.models.update_dict(target_model)
            col.merge_undo_entries(fixture_undo)
            migrated = col.get_note(migrated.id)
            migrated["MigrationSource"] = "unneeded old source archive"
            col.update_note(migrated)
            col.merge_undo_entries(fixture_undo)
            extra = col.new_note(model)
            extra["Front"], extra["Back"] = "色", "another source"
            col.add_note(extra, 1)
            extra_writing = extra.cards()[1]
            extra_writing.did = production_deck
            col.update_card(extra_writing)
            col.merge_undo_entries(fixture_undo)
            cleanup_plan = prepare_migration(col, rules[:1])
            apply_migration(col, cleanup_plan)
            assert "MigrationSource" not in col.get_note(migrated.id).keys()
            assert _schedule(col.get_card(ids[0])) == schedules[ids[0]]
            assert col.db.all("select * from revlog order by id") == before["revlog"]
            col.undo()
            assert col.get_note(migrated.id)["MigrationSource"] == "unneeded old source archive"
            col.undo()  # Remove the archive fixture and extra source note.
            col.undo()  # Undo the original migration.
            assert all(col.db.all(f"select * from {t} order by id") == before[t] for t in before)
            # A concurrent source edit invalidates approval without writing anything.
            plan = prepare_migration(col, rules)
            card = col.get_card(ids[0])
            card.due += 1
            col.update_card(card)
            try:
                apply_migration(col, plan)
            except ValueError as error:
                assert "changed" in str(error)
            else:
                raise AssertionError("Stale approval was accepted")
            card.due -= 1
            col.update_card(card)
            plan = prepare_migration(col, rules)
            rollback_before = {t: col.db.all(f"select * from {t} order by id") for t in before}
            original = col.update_card
            calls = 0

            def fail_second(card):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise RuntimeError("Injected transfer failure")
                return original(card)

            with patch.object(col, "update_card", fail_second):
                try:
                    apply_migration(col, plan)
                except RuntimeError as error:
                    assert "Injected" in str(error)
                else:
                    raise AssertionError("Injected failure did not fire")
            assert all(
                col.db.all(f"select * from {t} order by id") == rollback_before[t] for t in before
            )
            # Migrating one deck preserves the sibling in the other deck and its source note.
            plan = prepare_migration(col, rules[:1])
            apply_migration(col, plan)
            assert col.get_card(ids[1]).nid == source.id
            assert col.get_note(source.id)["Back"] == source["Back"]
            assert col.db.all("select * from revlog order by id") == before["revlog"]
            col.undo()

            class InlineOperation:
                def __init__(self, *, parent, op, success=None):
                    self.op, self.done = op, success

                def success(self, callback):
                    self.done = callback
                    return self

                def failure(self, callback):
                    self.failed = callback
                    return self

                def with_backend_progress(self, callback):
                    return self

                def run_in_background(self):
                    try:
                        result = self.op(col)
                    except Exception as error:
                        self.failed(error)
                    else:
                        self.done(result)

            mw.pm = SimpleNamespace(backupFolder=lambda: str(backups))
            mw.taskman = SimpleNamespace(run_on_main=lambda callback: callback())
            mw.progress = SimpleNamespace(update=lambda **_kwargs: None)
            with (
                patch("katanki.ui.migration.QueryOp", InlineOperation),
                patch("katanki.ui.migration.CollectionOp", InlineOperation),
                patch("katanki.ui.migration.MigrationDialog._refresh_after_migration") as refresh,
                patch("katanki.ui.migration.showInfo") as info,
                patch("katanki.ui.migration.showWarning") as warning,
            ):
                dialog = MigrationDialog(mw)
                assert not dialog.preview_button.isEnabled()
                assert all(not m.model.isEnabled() for m in dialog.mappings.values())
                dialog.preview()
                warning.assert_not_called()
                mapping = dialog.mappings["recognition"]
                mapping.deck.setCurrentIndex(mapping.deck.findData(1))
                mapping.model.setCurrentIndex(mapping.model.findData(model["id"]))
                mapping.field.setCurrentIndex(mapping.field.findData("Front"))
                dialog.preview()
                assert dialog.plan and len(dialog.plan.items) == 1
                assert dialog.apply_button.isEnabled()
                dialog.show()
                app.processEvents()
                dialog.grab().save("/tmp/katanki-migration.png")
                dialog.apply()
                warning.assert_not_called()
                info.assert_called_once()
                app.processEvents()
                refresh.assert_called_once()
                assert not dialog.apply_button.isEnabled()
                assert col.get_note(col.get_card(ids[0]).nid).note_type()[MODEL_MARKER] == (
                    "kanji-recognition"
                )
                dialog.reject()
            col.undo()
            # Both source decks identify parts without a separate category mapping.
            strokes = Path(directory) / "strokes"
            copytree(ROOT / "tests/fixtures/kanjivg", strokes)
            svg = strokes / "0666f.svg"
            svg.write_text(svg.read_text().replace('kvg:element="京"', 'kvg:element="⺡"'))
            mixed_settings = replace(
                settings,
                dictionaries=tuple(
                    replace(choice, path=str(strokes)) if choice.dataset_id == "kanjivg" else choice
                    for choice in settings.dictionaries
                ),
            )
            save_settings(col, mixed_settings)
            part = col.new_note(model)
            part["Front"], part["Back"], part["Meaning"] = "⺡", "old part", "water radical"
            col.add_note(part, 1)
            part_writing = part.cards()[1]
            part_writing.did = production_deck
            col.update_card(part_writing)
            part_ids = tuple(card.id for card in part.cards())
            mixed_schedules = {cid: _schedule(col.get_card(cid)) for cid in (*ids, *part_ids)}
            mixed = prepare_migration(col, rules)
            assert {item.identity.note_type for item in mixed.items} == {
                "kanji-recognition",
                "kanji-production",
                "primitive-recognition",
                "primitive-production",
            }, mixed.warnings
            apply_migration(col, mixed)
            assert set(col.find_cards("")) == set((*ids, *part_ids))
            for cid in (*ids, *part_ids):
                assert _schedule(col.get_card(cid)) == mixed_schedules[cid]
            assert col.db.all("select * from revlog order by id") == before["revlog"]
            col.undo()

        finally:
            col.close()
            mw.close()
            app.processEvents()
    print(
        f"PASS: Anki {anki.version}; original card IDs/history/scheduling, split modes, tags, "
        "progress, backup, stale approval, Undo, failure rollback, siblings, Parts and Qt"
    )


if __name__ == "__main__":
    main()
