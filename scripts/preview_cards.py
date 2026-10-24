"""Write an offline layout gallery using the exact card templates and styles."""

import argparse
import sys
from dataclasses import replace
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from katanki.dictionaries.adapters.kanjivg_svg import KanjiVgSvg  # noqa: E402
from katanki.dictionaries.words import PACK, bundled_words  # noqa: E402
from katanki.generation.cards import CSS, CardContent  # noqa: E402
from katanki.generation.planner import Identity  # noqa: E402
from katanki.generation.review import render_card_preview  # noqa: E402


def sample_cards():
    path = ROOT / "src/katanki/dictionaries/bundled/kanjivg.zip"
    visual = None
    if path.exists():
        with KanjiVgSvg(path) as provider:
            visual = provider.lookup_strokes("景")
    discovered = (
        "景色",
        "風景",
        "夜景",
        "背景",
        "絶景",
        "光景",
        "雪景色",
        "夕景",
        "春景色",
        "風景画",
        "景気回復",
    )
    defaults = bundled_words().lookup("景") if PACK.exists() else ()
    content = CardContent(
        Identity("kanji-recognition", "景"),
        "景",
        meanings=("scenery", "view"),
        readings=("ケイ",),
        components=("日", "京"),
        svg=visual.svg if visual else b"",
        prompt="scenery, view\n\n__色\n風__",
        examples=tuple(dict.fromkeys((*discovered, *defaults))),
        example_limit=2,
        discovered_examples=discovered,
        front_examples=discovered,
        back_examples=tuple(dict.fromkeys((*discovered, *defaults))),
        example_statuses=(
            ("景色", "learned"),
            ("風景", "new"),
            ("夜景", "learned"),
            ("背景", "relearning"),
            ("光景", "learning"),
            ("夕景", "new"),
        ),
        attribution=(
            "KanjiVG © Ulrich Apel and contributors · CC BY-SA 3.0. "
            "SVG sanitized for embedding. https://kanjivg.tagaini.net/",
            "Example word statuses are illustrative.",
        ),
    )
    for mode in ("recognition", "production"):
        yield replace(content, identity=Identity("kanji-" + mode, "景"))
    for mode in ("recognition", "production"):
        yield CardContent(
            Identity("primitive-" + mode, "日"),
            "日",
            prompt="sun",
            examples=("景", "晴", "時"),
            attribution=("Layout sample; stroke data omitted to demonstrate the fallback.",),
        )


def document(markup, *, dark=False):
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<style>{CSS}</style></head>"
        f'<body class="card{" nightMode" if dark else ""}">{markup}</body></html>'
    )


def gallery():
    cards = []
    for content in sample_cards():
        for side, markup in zip(("Front", "Back"), render_card_preview(content), strict=True):
            for dark in (False, True):
                title = f"{content.identity.note_type} · {side} · {'Dark' if dark else 'Light'}"
                cards.append(
                    f"<section><h2>{escape(title)}</h2>"
                    f'<iframe title="{escape(title)}" srcdoc="'
                    + escape(document(markup, dark=dark), quote=True)
                    + '"></iframe></section>'
                )
    return (
        '<!doctype html><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>Katanki card layouts</title><style>"
        "body{font-family:system-ui;margin:32px;background:#e9edf4;color:#263047}"
        "main{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,360px),1fr));"
        "gap:24px}section{min-width:0}h2{font-size:13px;font-weight:500}"
        "iframe{width:100%;height:1100px;border:1px solid #ccd3df;border-radius:16px;"
        "background:white;box-sizing:border-box}</style>"
        "<h1>Katanki · Review cards</h1>"
        "<p>Standalone front and back templates. Resize the window to compare layouts. "
        "Word statuses are illustrative; fronts use only Anki words with a clue limit of 2. "
        "Backs include the full "
        "sample vocabulary and configured dictionary suggestions; expand Show more words "
        "for long lists.</p>"
        "<main>" + "".join(cards) + "</main>"
        """<script>
document.querySelectorAll('iframe').forEach(function(frame) {
  frame.addEventListener('load', function() {
    var body = frame.contentDocument.body;
    function resize() {
      frame.style.height = Math.ceil(body.getBoundingClientRect().height + 2) + 'px';
    }
    var observer = new ResizeObserver(resize);
    observer.observe(body);
    resize();
  });
});
</script>"""
    )


def write_gallery(output):
    directory = (ROOT / "dist").resolve()
    output = (directory / output).resolve()
    if not output.is_relative_to(directory):
        raise ValueError("Preview output must be inside the project's dist directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(gallery(), encoding="utf-8")
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("katanki-card-layout-preview.html"),
        help="Output path within the project's dist directory (relative to dist)",
    )
    args = parser.parse_args(argv)
    try:
        output = write_gallery(args.output)
    except ValueError as error:
        parser.error(str(error))
    print(output)


if __name__ == "__main__":
    main()
