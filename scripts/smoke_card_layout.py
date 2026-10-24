"""Verify standalone exported cards in a clean collection and an offline Qt webview."""

import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_QUICK_BACKEND", "software")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")


def exported_cards(directory):
    from anki.collection import (
        Collection,
        ExportAnkiPackageOptions,
        ImportAnkiPackageRequest,
        NoteIdsLimit,
    )

    from katanki.anki.collection import selected_notes
    from katanki.anki.generation import apply_generation, preview_generation
    from katanki.common.models import DiscoveryReport, KanjiEntry, ScanSelection
    from katanki.config import CardSettings, Settings, load_settings, save_settings
    from katanki.generation.discovery import scan_notes
    from scripts.preview_cards import sample_cards

    source = Collection(str(directory / "source.anki2"))
    try:
        basic = source.models.by_name("Basic")
        for word, stage in (("景色", 2), ("風景", 0), ("背景", 3), ("光景", 1)):
            note = source.new_note(basic)
            note["Front"] = word
            source.add_note(note, 1)
            card = note.cards()[0]
            card.type = stage
            if stage == 2:
                card.queue, card.ivl, card.reps = 2, 30, 5
            source.update_card(card)
        scan = scan_notes(selected_notes(source, ScanSelection((1,), basic["id"], ("Front",))))
        assert dict(scan.vocabulary_statuses) == {
            "景色": "learned",
            "風景": "new",
            "背景": "relearning",
            "光景": "learning",
        }
        content = next(sample_cards())
        report = DiscoveryReport(
            scan, (KanjiEntry("景", ("ケイ",), (), ("scenery", "view")),), (), (), True, ()
        )
        options = CardSettings(
            example_source="discovered_and_default",
            front_example_source="discovered",
            example_limit=1,
        )
        saved_settings = Settings(cards=(options, options, CardSettings()))
        save_settings(source, saved_settings)
        preview = preview_generation(
            source,
            report,
            recognition=("景",),
            production=("景",),
            include_primitives=False,
            card_settings={"recognition": options, "production": options},
            word_suggestions=SimpleNamespace(
                lookup=lambda char: (
                    "景色",
                    "風景",
                    "背景",
                    "光景",
                    "夜景",
                    "情景",
                    "景勝",
                    "景品",
                    "景気",
                    "景観",
                    "不景気",
                    "好景気",
                    "雪景色",
                    "風景画",
                    "夕景",
                )
            ),
        )
        # Include real inline SVG data to exercise exported stroke controls.
        from dataclasses import replace

        preview = replace(
            preview,
            contents=tuple(
                replace(item, svg=content.svg, components=content.components)
                for item in preview.contents
            ),
        )
        assert apply_generation(source, preview, deck_id=1).created == 2
        nids = source.find_notes('"note:Kanji Katanki*"')
        assert len(nids) == 2
        # User-first deduplication must retain the known word's saved status.
        for nid in nids:
            note = source.get_note(nid)
            note["UserExamples"] = "<div>景色</div><div>絶景</div>"
            source.update_note(note)
        package = directory / "cards.apkg"
        source.export_anki_package(
            out_path=str(package),
            options=ExportAnkiPackageOptions(with_media=True, with_scheduling=True),
            limit=NoteIdsLimit(nids),
        )
        before = source.db.all("select * from cards order by id")
        assert apply_generation(source, preview, deck_id=1).created == 0
        assert source.db.all("select * from cards order by id") == before
    finally:
        source.close()
    reopened = Collection(str(directory / "source.anki2"))
    try:
        assert load_settings(reopened) == saved_settings
    finally:
        reopened.close()
    clean = Collection(str(directory / "clean.anki2"))
    try:
        clean.import_anki_package(ImportAnkiPackageRequest(package_path=str(package)))
        nids = clean.find_notes("")
        assert len(nids) == 2  # Source vocabulary was not exported.
        cards = []
        for nid in nids:
            note = clean.get_note(nid)
            card = note.cards()[0]
            cards.append((note.note_type()["katanki_note_type"], card.question(), card.answer()))
        assert all("data-status=" in back and "{{" not in back for _, _, back in cards)
        return cards
    finally:
        clean.close()


def webview_checks(cards, screenshots):
    from aqt.qt import (
        QApplication,
        QCoreApplication,
        QEvent,
        QEventLoop,
        QTimer,
        QWebEnginePage,
        QWebEngineView,
        qInstallMessageHandler,
    )
    from PyQt6.QtWebEngineCore import QWebEngineUrlRequestInterceptor

    from scripts.preview_cards import document

    qInstallMessageHandler(lambda level, context, message: print(message, flush=True))
    app = QApplication.instance() or QApplication(["katanki-layout-smoke"])
    errors, requests = [], []

    class Page(QWebEnginePage):
        def javaScriptConsoleMessage(self, level, message, line, source):
            if level == self.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
                errors.append(message)

    class Offline(QWebEngineUrlRequestInterceptor):
        def interceptRequest(self, info):
            if info.requestUrl().scheme() in {"http", "https"}:
                requests.append(info.requestUrl().toString())
                info.block(True)

    view = QWebEngineView()
    page = Page(view)
    view.setPage(page)
    offline = Offline(page)
    page.profile().setUrlRequestInterceptor(offline)

    def render(html, javascript):
        loop, results = QEventLoop(), []

        def finished(ok):
            if not ok:
                loop.quit()
                return

            def checked(result):
                results.append(result)
                loop.quit()

            page.runJavaScript(javascript, checked)

        view.loadFinished.connect(finished)
        view.setHtml(html)
        QTimer.singleShot(10_000, loop.quit)
        loop.exec()
        view.loadFinished.disconnect(finished)
        assert results and results[0], (results, errors)
        return results[0]

    try:
        # Reproduce the editor corruption behind the reported invalid-record
        # warning, then prove the new encoding survives the same HTML round trip.
        import json

        from katanki.generation.examples import decode_state, encode_state, recover_editor_state

        fields = {
            "VocabExamples": '<div data-source="vocabulary" data-status="new">一度</div>',
            "Prompt": "one &lt;two&gt;<br>__度",
        }
        legacy = json.dumps({"version": 1, "fields": fields}, ensure_ascii=False)
        safe = encode_state(fields)
        editor = render(
            document("<p>Editor round trip</p>"),
            """(function() {
          var old = document.createElement('div'), safe = document.createElement('div');
          old.contentEditable = safe.contentEditable = 'true';
          old.innerHTML = """
            + json.dumps(legacy)
            + ";safe.innerHTML = "
            + json.dumps(safe)
            + ";"
            "return {old: old.innerHTML, safe: safe.innerHTML};})()",
        )
        try:
            json.loads(editor["old"])
        except ValueError:
            pass
        else:
            raise AssertionError("Legacy raw JSON did not reproduce the editor corruption")
        assert decode_state(editor["safe"], fields) == fields
        assert recover_editor_state(editor["old"], fields) == fields
        print("PASS: editor damage is reversible; escaped baseline survives unchanged")
        from katanki.config import CardSettings
        from katanki.ui.card_settings import CardSettingsPanel

        for category in ("recognition", "production"):
            panel = CardSettingsPanel(category, CardSettings())
            assert panel.settings() == CardSettings()  # Opening/saving preserves legacy choices.
            panel.front_source.setCurrentIndex(panel.front_source.findData("discovered"))
            panel.back_source.setCurrentIndex(panel.back_source.findData("discovered_and_default"))
            saved = panel.settings()
            assert saved.front_source == "discovered"
            assert saved.example_source == "discovered_and_default"
            restored = CardSettingsPanel(category, saved)
            assert restored.settings() == saved
            panel.resize(760, 720)
            panel.show()
            app.processEvents()
            panel.grab().save(str(screenshots / f"{category}-example-settings.png"))
            panel.close()
            panel.deleteLater()
            restored.deleteLater()
        print("PASS: independent front/back controls save and reopen with old choices preserved")
        for width in (360, 900):
            view.resize(width, 1300)
            view.show()
            app.processEvents()
            for key, front, back in cards:
                for dark in (False, True):
                    result = render(
                        document(front, dark=dark),
                        """(function() {
                      return {meaning: document.querySelector('.production-meaning')?.textContent,
                        clues: Array.from(document.querySelectorAll('.clue-chip'))
                          .map(n => n.textContent),
                        overflow: document.documentElement.scrollWidth > window.innerWidth,
                        bridge: typeof pycmd, text: document.body.innerText};
                    })()""",
                    )
                    assert not result["overflow"], (width, result)
                    assert result["bridge"] == "undefined"
                    assert "Write the" not in result["text"]
                    if key.endswith("production"):
                        assert result["meaning"] == "scenery, view"
                        assert result["clues"] == ["光__"]
                    else:
                        # UserExamples are rendered live on recognition fronts;
                        # limits and source choices still exclude dictionary-only words.
                        assert result["clues"] == ["景色"]
                    assert not {"夜景", "情景", "景勝"} & set(result["clues"])
                    result = render(
                        document(back, dark=dark),
                        """(function() {
                      var words = Array.from(document.querySelectorAll('.word-chip'));
                      var numbers = document.querySelector('button[onclick^="katankiNumbers"]');
                      var play = document.querySelector('button[onclick^="katankiPlay"]');
                      katankiNumbers(numbers);
                      var count = document.querySelectorAll('.katanki-number').length;
                      katankiNumbers(numbers);
                      katankiPlay(play);
                      return {words: words.map(n => [n.textContent, n.dataset.status]),
                        paths: document.querySelectorAll('.strokes svg path').length,
                        numbers: count, animations: document.getAnimations().length,
                        cleared: document.querySelectorAll('.katanki-number').length === 0,
                        repeated: !!document.querySelector('.question-card'),
                        overflow: document.documentElement.scrollWidth > window.innerWidth,
                        columns: getComputedStyle(document.querySelector('.answer-details'))
                          .gridTemplateColumns,
                        color: getComputedStyle(words[0]).color,
                        styles: words.slice(0, 4).map(n => [getComputedStyle(n).color,
                          getComputedStyle(n).borderStyle]),
                        initial: document.querySelectorAll('.example-output .word-chip').length,
                        extra: document.querySelectorAll('.more-word-output .word-chip').length,
                        total: document.querySelector('.word-count').textContent,
                        expandable: !document.querySelector('.more-words').hidden};
                    })()""",
                    )
                    assert result["words"] == [
                        ["景色", "learned"],
                        ["背景", "relearning"],
                        ["光景", "learning"],
                        ["風景", "new"],
                        ["絶景", "missing"],
                        ["夜景", "missing"],
                        ["情景", "missing"],
                        ["景勝", "missing"],
                        ["景品", "missing"],
                        ["景気", "missing"],
                        ["景観", "missing"],
                        ["不景気", "missing"],
                        ["好景気", "missing"],
                        ["雪景色", "missing"],
                        ["風景画", "missing"],
                        ["夕景", "missing"],
                    ], result
                    assert result["initial"] == 12 and result["extra"] == 4, result
                    assert result["total"] == "16" and result["expandable"], result
                    assert len({tuple(style) for style in result["styles"]}) == 4, result
                    expanded = QEventLoop()
                    checks = []
                    page.runJavaScript(
                        """(function() {
                          var more = document.querySelector('.more-words');
                          more.open = true;
                          return document.querySelector('.more-word-output').getBoundingClientRect()
                            .height > 0;
                        })()""",
                        lambda value, checks=checks, expanded=expanded: (
                            checks.append(value),
                            expanded.quit(),
                        ),
                    )
                    QTimer.singleShot(10_000, expanded.quit)
                    expanded.exec()
                    assert checks == [True], checks
                    assert not result["overflow"] and not result["repeated"], result
                    assert result["paths"] == result["numbers"] > 0, result
                    assert result["cleared"] and result["animations"] > 0, result
                    if width == 360:
                        assert " " not in result["columns"], result
                    if key.endswith("recognition"):
                        page.runJavaScript("document.getAnimations().forEach(a => a.finish())")
                        paint = QEventLoop()
                        QTimer.singleShot(250, paint.quit)
                        paint.exec()
                        view.grab().save(
                            str(
                                screenshots / f"card-back-{width}-{'dark' if dark else 'light'}.png"
                            )
                        )
        assert not errors, errors
        assert not requests, requests
        print("PASS: clean export/import, no source notes/bridge/network; all words/statuses;")
        print("front/back, stroke controls, narrow/wide layouts and light/dark rendering")
    finally:
        view.close()
        page.profile().setUrlRequestInterceptor(None)
        view.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def main():
    with TemporaryDirectory(prefix="katanki-layout-") as temporary:
        cards = exported_cards(Path(temporary))
        webview_checks(cards, Path(temporary))


if __name__ == "__main__":
    main()
