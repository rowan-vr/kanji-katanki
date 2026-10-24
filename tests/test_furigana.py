"""Reading lookup, independent defaults, and safe persisted review data."""

from katanki.config import Settings, from_dict
from katanki.dictionaries.words import WordSuggestions
from katanki.generation.cards import CardContent
from katanki.generation.examples import words_for_side
from katanki.generation.planner import Identity


def test_furigana_defaults_and_saved_choices():
    settings = Settings()
    assert settings.card_settings("production").front_furigana
    assert not settings.card_settings("recognition").front_furigana
    assert all(settings.card_settings(c).furigana for c in ("production", "recognition"))
    saved = settings.to_dict()
    saved["cards"]["production"]["front_furigana"] = False
    saved["cards"]["recognition"]["furigana"] = False
    restored = from_dict(saved)
    assert not restored.card_settings("production").front_furigana
    assert restored.card_settings("production").furigana
    assert not restored.card_settings("recognition").furigana


def test_readings_keep_highest_priority_variant():
    words = WordSuggestions((("時間", "じかん", 10), ("時間", "とき", 1)))
    assert words.readings("時") == {"時間": "じかん"}
    assert words.readings("無") == {}


def test_readings_are_escaped_without_changing_words_or_masked_clues():
    card = CardContent(
        Identity("kanji-production", "時"),
        "時",
        examples=("時間", "時々"),
        example_readings=(("時間", "じかん"), ("時々", "<unsafe>")),
        front_furigana=True,
        back_furigana=False,
    )
    html = card.fields()["VocabExamples"]
    assert 'data-reading="じかん"' in html
    assert 'data-reading="&lt;unsafe&gt;"' in html
    assert 'data-masked="__間"' in html
    assert 'data-front-furigana="true"' in html
    assert 'data-back-furigana="false"' in html
    assert words_for_side(html, "back") == ("時間", "時々")


def test_kana_alignment_and_masking_in_actual_review_renderer():
    """Run the shared card JavaScript against a small DOM with Node."""
    import json
    import shutil
    import subprocess

    import pytest

    from katanki.generation.furigana import SCRIPT

    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is needed to exercise the review renderer")
    cases = [
        ("七つ", "ななつ", None, [["七", "なな"], ["つ", ""]]),
        ("七日", "なのか", None, [["七日", "なのか"]]),
        ("食べる", "たべる", None, [["食", "た"], ["べる", ""]]),
        ("お祝い", "おいわい", None, [["お", ""], ["祝", "いわ"], ["い", ""]]),
        (
            "取り扱う",
            "とりあつかう",
            None,
            [["取", "と"], ["り", ""], ["扱", "あつか"], ["う", ""]],
        ),
        ("食べる", "たべる", "食", [["__", "た"], ["べる", ""]]),
        ("時々", "ときどき", "時", [["__々", "ときどき"]]),
        ("カレー", "かれー", None, [["カレー", ""]]),
        # Ambiguous kana boundaries and irregular readings retain a group reading.
        ("甲あ乙", "かああき", None, [["甲あ乙", "かああき"]]),
        ("大人しい", "おとなしい", None, [["大人", "おとな"], ["しい", ""]]),
        ("今日", "きょう", None, [["今日", "きょう"]]),
        ("一日", "ついたち", None, [["一日", "ついたち"]]),
        ("<unsafe>", "<reading>", None, [["<unsafe>", "<reading>"]]),
    ]
    harness = r"""
class Node {
  constructor(tag, text) { this.tag = tag; this.text = text || ''; this.children = []; }
  set textContent(text) { this.text = text; this.children = []; }
  get textContent() { return this.text + this.children.map(n => n.textContent).join(''); }
  appendChild(node) { this.children.push(node); }
  classList = {toggle: (name, enabled) => { this.annotated = enabled; }};
}
const document = {
  createElement: tag => new Node(tag),
  createTextNode: text => new Node('#text', text)
};
const results = CASES.map(([word, reading, target]) => {
  const node = new Node('div');
  katankiFurigana(node, word, reading, target);
  return node.children.map(n => n.tag === 'ruby'
    ? [n.children[0].textContent, n.children[1].textContent] : [n.textContent, '']);
});
process.stdout.write(JSON.stringify(results));
"""
    script = SCRIPT + harness.replace("CASES", json.dumps(cases, ensure_ascii=False))
    result = subprocess.run([node], input=script, encoding="utf-8", capture_output=True, check=True)
    assert json.loads(result.stdout) == [case[3] for case in cases]
