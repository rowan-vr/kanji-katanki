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
                    spec.back,
                    count=1,
                    flags=re.DOTALL,
                )
                template = collection.models.new_template("Recognition")
                template["qfmt"] = spec.front
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
        (1, True, ["景色"]),
        (2, True, ["景色", "景観"]),
        (0, True, ["景色", "景観", "風景"]),
        (5, False, []),
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


if __name__ == "__main__":
    main()
