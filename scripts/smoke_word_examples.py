"""Verify example-field/template migration and Undo in a disposable real Anki collection."""

import re
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main():
    from anki.collection import Collection

    from katanki.anki.generation import apply_generation, preview_generation
    from katanki.anki.identities import MODEL_MARKER
    from katanki.common.models import DiscoveryReport, KanjiEntry, ScanResult
    from katanki.config import CardSettings, Settings
    from katanki.generation import legacy_cards
    from katanki.generation.cards import note_type_spec

    for customized in (False, True):
        with TemporaryDirectory(prefix="katanki-word-migration-") as directory:
            collection = Collection(str(Path(directory) / "collection.anki2"))
            try:
                spec = note_type_spec("kanji-recognition")
                model = collection.models.new(spec.name)
                model[MODEL_MARKER] = spec.key
                for name in spec.fields:
                    if name not in {
                        "VocabExamples",
                        "UserExamples",
                        "ExampleLimit",
                        "KatankiExamplesState",
                    }:
                        collection.models.add_field(model, collection.models.new_field(name))
                legacy_back = re.sub(
                    r'<div class="katanki-examples".*?</script>\n',
                    "",
                    legacy_cards.BACK,
                    count=1,
                    flags=re.DOTALL,
                )
                template = collection.models.new_template("Recognition")
                template["qfmt"] = legacy_cards.front(spec.key)
                template["afmt"] = "Custom {{Display}}" if customized else legacy_back
                collection.models.add_template(model, template)
                added = collection.models.add_dict(model)
                model = collection.models.get(added.id)
                old = collection.new_note(model)
                old["Character"], old["Display"] = "間", "間"
                collection.add_note(old, 1)
                before_cards = collection.db.all("select * from cards order by id")
                before_fields = list(old.fields)
                report = DiscoveryReport(
                    ScanResult(1, ("時",)),
                    (KanjiEntry("時", (), (), ("time",)),),
                    (),
                    (),
                    True,
                    (),
                )
                settings = Settings(
                    cards=tuple(
                        CardSettings(example_source="discovered_and_default") for _ in range(3)
                    )
                )
                preview = preview_generation(
                    collection,
                    report,
                    generation_settings=settings,
                    fallback_deck_id=1,
                    recognition=("時",),
                    production=(),
                    include_primitives=False,
                )
                assert "時間" in preview.contents[0].examples
                result = apply_generation(collection, preview)
                assert result.created == 1
                updated = collection.models.get(added.id)
                assert updated["tmpls"][0]["afmt"] == (
                    "Custom {{Display}}" if customized else spec.back
                )
                note = collection.get_note(old.id)
                assert note.fields[: len(before_fields)] == before_fields
                assert (
                    collection.db.all("select * from cards where nid = ?", old.id) == before_cards
                )
                collection.undo()
                assert collection.db.all("select * from cards order by id") == before_cards
                assert collection.get_note(old.id).fields == before_fields
                assert "VocabExamples" not in {
                    field["name"] for field in collection.models.get(added.id)["flds"]
                }
            finally:
                collection.close()
    print("PASS: offline default suggestions, stock/custom template migration, scheduling and Undo")


def exercise_example_rendering(mw):
    """Check ordering, deduplication, all/limited/hidden output in the real webview."""
    from aqt.qt import QEventLoop, QTimer
    from aqt.webview import AnkiWebView

    from katanki.generation.cards import CardContent
    from katanki.generation.planner import Identity
    from katanki.generation.review import render_card_preview

    for limit, visible, expected in (
        (1, True, ["景色", "景観", "風景"]),
        (2, True, ["景色", "景観", "風景"]),
        (0, True, ["景色", "景観", "風景"]),
        (5, False, ["景色", "景観", "風景"]),
    ):
        content = CardContent(
            Identity("kanji-recognition", "景"),
            "景",
            examples=("景色", "風景"),
            example_limit=limit,
            show_examples=visible,
        )
        _, back = render_card_preview(content)
        back = back.replace(
            '<div class="user-examples" hidden></div>',
            '<div class="user-examples" hidden><div>景色</div><div>景観</div></div>',
        )
        view = AnkiWebView(parent=mw)
        loop, timer, results = QEventLoop(), QTimer(mw), []
        timer.setInterval(50)

        def checked(result, results=results, loop=loop):
            if result is not None:
                results.append(result)
                loop.quit()

        def poll(view=view, checked=checked):
            view.evalWithCallback(
                "Array.from(document.querySelectorAll('.example-output div'))"
                ".map(function(n) { return n.textContent; })",
                checked,
            )

        timer.timeout.connect(poll)
        view.stdHtml(back)
        timer.start()
        QTimer.singleShot(10_000, loop.quit)
        try:
            loop.exec()
        finally:
            timer.stop()
            view.cleanup()
            view.deleteLater()
        assert results and results[0] == expected, (limit, visible, results)
    print("PASS: example rendering, user ordering, duplicate removal, limits and visibility")


def exercise_early_stock_upgrade():
    """The first installed polished template must not mislabel new source words."""
    from anki.collection import Collection

    from katanki.anki.example_refresh import apply_example_refresh, plan_example_refresh
    from katanki.anki.identities import MODEL_MARKER
    from katanki.common.models import DiscoveryReport, KanjiEntry, ScanResult
    from katanki.config import DictionaryChoice, Settings
    from katanki.generation import legacy_layout_v1 as previous
    from katanki.generation.cards import CSS, CardContent, note_type_spec
    from katanki.generation.planner import Identity

    with TemporaryDirectory(prefix="katanki-early-layout-") as temporary:
        col = Collection(str(Path(temporary) / "collection.anki2"))
        try:
            spec = note_type_spec("kanji-recognition")
            model = col.models.new(spec.name)
            model[MODEL_MARKER] = spec.key
            model["css"] = previous.EARLY_CSS
            for name in spec.fields:
                col.models.add_field(model, col.models.new_field(name))
            template = col.models.new_template("Recognition")
            label = "Kanji · Recognition"
            template["qfmt"] = previous.RECOGNITION_FRONT.replace("{{CardLabel}}", label)
            template["afmt"] = (
                previous.EARLY_BACK.replace("{{CardLabel}}", label)
                .replace("{{WordsLabel}}", "Words")
                .replace("{{WordLegend}}", previous.WORD_LEGEND.rstrip("\n"))
            )
            original_back = template["afmt"]
            col.models.add_template(model, template)
            mid = col.models.add_dict(model).id
            note = col.new_note(col.models.get(mid))
            content = CardContent(
                Identity(spec.key, "丈"),
                "丈",
                meanings=("length",),
                examples=("丈夫",),
                discovered_examples=("丈夫",),
                example_statuses=(("丈夫", "new"),),
            )
            for name, value in content.fields().items():
                note[name] = value
            col.add_note(note, 1)
            fields_before = dict(col.get_note(note.id).items())
            cards_before = col.db.all("select * from cards order by id")
            report = DiscoveryReport(
                ScanResult(1, ("丈",), ("丈夫",), vocabulary_statuses=(("丈夫", "new"),)),
                (KanjiEntry("丈", (), (), ("length",)),),
                (),
                (),
                True,
                (),
            )
            settings = Settings(
                dictionaries=tuple(
                    DictionaryChoice(name, "disabled")
                    for name in ("kanjidic2", "kanjivg", "jitendex")
                )
            )
            plan = plan_example_refresh(col, report, settings)
            assert len(plan.updates) == 1 and not plan.updates[0].migration
            assert apply_example_refresh(col, plan).updated == 1
            upgraded = col.models.get(mid)
            assert upgraded["tmpls"][0]["afmt"] == spec.back
            assert upgraded["css"] == CSS
            assert dict(col.get_note(note.id).items()) == fields_before
            assert col.db.all("select * from cards order by id") == cards_before
            assert "new: 'New'" in col.get_note(note.id).cards()[0].answer()
            assert not plan_example_refresh(col, report, settings).updates
            col.undo()
            assert col.models.get(mid)["tmpls"][0]["afmt"] == original_back
            assert col.models.get(mid)["css"] == previous.EARLY_CSS
            assert col.db.all("select * from cards order by id") == cards_before
            print("PASS: earliest polished stock layout upgrades; new word status, fields and Undo")
        finally:
            col.close()


if __name__ == "__main__":
    main()
    exercise_early_stock_upgrade()
