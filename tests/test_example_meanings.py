"""Dictionary snapshots and portable definition popup behavior."""

import json
import shutil
import subprocess
from dataclasses import replace
from zipfile import ZipFile

import pytest

from katanki.dictionaries.adapters.jitendex_yomitan import JitendexYomitan, convert
from katanki.dictionaries.words import WordSuggestions
from katanki.generation.cards import CSS, note_type_spec
from katanki.generation.layout_fingerprints import PRE_MEANINGS_PAIRS, PRE_MEANINGS_STYLE
from katanki.generation.preview import build_preview
from katanki.generation.template_updates import upgrade_stock_layout
from katanki.generation.word_popup import SCRIPT


def test_definitions_include_source_words_outside_suggestion_filter_and_cache(
    tmp_path, monkeypatch
):
    from katanki.dictionaries import updates
    from katanki.dictionaries.adapters import jitendex_yomitan as adapter

    monkeypatch.setattr(updates, "USER_DATA", tmp_path / "cache")
    path = tmp_path / "dictionary.zip"
    gloss = {
        "type": "structured-content",
        "content": [
            {
                "data": {"content": "glossary"},
                "content": [
                    {"tag": "li", "content": "today"},
                    {"tag": "li", "content": "this day"},
                ],
            },
            {"data": {"content": "extra-info"}, "content": "unwanted attribution"},
        ],
    }
    with ZipFile(path, "w") as archive:
        archive.writestr(
            "index.json", json.dumps({"format": 3, "revision": "test", "title": "Test"})
        )
        archive.writestr(
            "term_bank_1.json",
            json.dumps(
                [
                    ["今日", "きょう", "", "", 0, [gloss], 1, ""],
                    ["今日", "こんにち", "", "", 0, ["nowadays"], 2, ""],
                ]
            ),
        )
    payload, _ = convert(path)
    assert json.loads(payload)["words"] == []
    provider = JitendexYomitan(path)
    assert provider.definitions("今日", "きょう") == ("today; this day",)
    assert provider.definitions("今日", "こんにち") == ("nowadays",)
    assert provider.definitions("今日", "unknown") == ()
    assert provider.definitions("今日") == ()
    adapter._suggestion_cache.clear()
    monkeypatch.setattr(adapter, "convert", lambda *a, **k: pytest.fail("cache was not used"))
    assert provider.definitions("今日", "こんにち") == ("nowadays",)


def test_preview_embeds_definitions_with_furigana_disabled():
    from test_word_suggestions import discovery

    from katanki.config import CardSettings

    provider = WordSuggestions(
        [("時間割", "じかんわり", 200)],
        [("時間割", "じかんわり", ["timetable", "<script>unsafe</script>"])],
    )
    preview = build_preview(
        discovery(),
        (),
        recognition=("時",),
        production=(),
        include_primitives=False,
        word_suggestions=provider,
        card_settings={"recognition": CardSettings(furigana=False, front_furigana=False)},
    )
    card = preview.contents[0]
    assert card.example_meanings == (("時間割", ("timetable", "<script>unsafe</script>")),)
    html = card.fields()["VocabExamples"]
    assert 'data-meaning="timetable\n&lt;script&gt;unsafe&lt;/script&gt;"' in html
    assert 'data-back-furigana="false"' in html
    assert "Jitendex" in card.fields()["Attribution"]
    assert "<script>unsafe</script>" not in html
    assert replace(card, example_meanings=()).fields()["VocabExamples"] != html


@pytest.mark.parametrize("key", PRE_MEANINGS_PAIRS)
def test_previous_stock_layout_is_recognized_for_refresh(key, monkeypatch):
    from types import SimpleNamespace

    from katanki.generation import template_updates

    front_hash, back_hash = PRE_MEANINGS_PAIRS[key]
    hashes = {
        b"previous front": front_hash,
        b"previous back": back_hash,
        b"previous style": PRE_MEANINGS_STYLE,
    }
    real_hash = template_updates.sha256
    monkeypatch.setattr(
        template_updates,
        "sha256",
        lambda value: (
            SimpleNamespace(hexdigest=lambda: hashes[value])
            if value in hashes
            else real_hash(value)
        ),
    )
    model = {
        "tmpls": [{"qfmt": "previous front", "afmt": "previous back"}],
        "css": "previous style",
    }
    assert upgrade_stock_layout(model, key)
    assert model["tmpls"][0]["afmt"] == note_type_spec(key).back
    assert model["css"] == CSS


@pytest.mark.parametrize("width", [390, 1000])
def test_popup_opens_escapes_text_closes_and_restores_focus(width):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is not installed")
    harness = r"""
class Element {
  constructor() { this.children = []; this.style = {}; this.attrs = {}; this.events = {};
    this.offsetWidth = 380; this.offsetHeight = 200; this.dataset = {}; }
  appendChild(child) { this.children.push(child); }
  setAttribute(k, v) { this.attrs[k] = v; }
  addEventListener(k, fn) { this.events[k] = fn; }
  focus() { focused = this; }
  getBoundingClientRect() { return {left: 950, bottom: 760}; }
}
var focused, document = {createElement: () => new Element()};
var window = {innerWidth: WIDTH, innerHeight: 800};
var source = new Element();
source.textContent = '今日';
source.dataset = {reading: 'きょう', meaning: 'today\n<script>text only</script>'};
var root = new Element();
root.querySelectorAll = () => [source];
SCRIPT
var button = new Element();
openDefinition(button, '今日');
if (overlay.hidden || heading.textContent !== '今日【きょう】') throw Error('not opened');
if (definitions.children[0].children[1].textContent !== '<script>text only</script>')
  throw Error('definition not rendered as text');
if (focused !== close || button.attrs['aria-expanded'] !== 'true') throw Error('focus');
if (WIDTH > 600 && popup.style.left !== '608px') throw Error('viewport bounds');
overlay.events.keydown({key: 'Escape', preventDefault(){}, stopPropagation(){}});
if (!overlay.hidden || focused !== button) throw Error('dismissal');
openDefinition(button, 'missing');
if (definitions.textContent !== 'Definition unavailable.') throw Error('fallback');
overlay.onclick({target: overlay, preventDefault(){}, stopPropagation(){}});
if (!overlay.hidden) throw Error('outside tap');
var chip = new Element(), activations = 0;
bindWordTap(chip, function() { activations++; });
if (!chip.className.includes('tappable')) throw Error('native tap-zone exclusion missing');
var prevented = 0, stopped = 0;
function touch(points) { return {touches: points,
  preventDefault() { prevented++; }, stopPropagation() { stopped++; }}; }
chip.events.touchstart(touch([{clientX: 20, clientY: 30}]));
chip.events.touchend(touch([]));
if (activations !== 1 || prevented !== 1 || stopped !== 2) throw Error('tap leaked');
chip.onclick(touch([]));
if (activations !== 1) throw Error('duplicate synthetic click');
chip.events.touchstart(touch([{clientX: 20, clientY: 30}]));
chip.events.touchmove(touch([{clientX: 20, clientY: 90}]));
chip.events.touchend(touch([]));
if (activations !== 1) throw Error('scroll opened popup');
chip.events.touchstart(touch([{clientX: 20, clientY: 30}]));
chip.events.touchcancel(touch([]));
chip.events.touchend(touch([]));
if (activations !== 1) throw Error('cancelled gesture opened popup');

"""
    script = harness.replace("SCRIPT", SCRIPT).replace("WIDTH", str(width))
    subprocess.run([node], input=script, text=True, capture_output=True, check=True)


def previous_click_layout(template):
    """Reconstruct the released popup before touch handlers were added."""
    import re

    template = re.sub(
        r"  function bindWordTap\(element, activate\) \{.*?(?=  var meaningNodes)",
        "",
        template,
        flags=re.DOTALL,
    )
    return (
        template.replace(
            "  bindWordTap(close, dismiss);", "  close.addEventListener('click', dismiss);"
        )
        .replace(
            "  bindWordTap(overlay, function(event) {",
            "  overlay.addEventListener('click', function(event) {\n    event.stopPropagation();",
        )
        .replace(
            "      bindWordTap(line, function(event) {",
            "      line.addEventListener('click', function(event) {\n"
            "        event.stopPropagation();",
        )
    )


@pytest.mark.parametrize("key", PRE_MEANINGS_PAIRS)
def test_installed_native_button_popup_upgrades_templates_and_styles(key):
    """Refresh must recognize the popup version already installed by users."""
    from copy import deepcopy
    from hashlib import sha256

    from katanki.generation.layout_fingerprints import (
        NATIVE_BUTTON_POPUP_PAIRS,
        NATIVE_BUTTON_POPUP_STYLE,
    )

    keyboard = """      line.addEventListener('keydown', function(event) {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          event.stopPropagation();
          openDefinition(line, entry.word);
        }
      });
"""

    def native_buttons(template):
        return (
            template.replace(
                "var line = document.createElement('div');",
                "var line = document.createElement(interactive ? 'button' : 'div');",
            )
            .replace(
                "      line.setAttribute('role', 'button');\n      line.tabIndex = 0;",
                "      line.type = 'button';",
            )
            .replace(keyboard, "")
        )

    spec = note_type_spec(key)
    front, back = (
        native_buttons(previous_click_layout(value)) for value in (spec.front, spec.back)
    )
    old_css = CSS.replace(
        ".word-chip.word-definition {cursor: pointer;}",
        ".word-chip.word-definition {font-family: inherit; min-height: 44px;\n"
        "  cursor: pointer; appearance: none;}",
    )
    assert (
        tuple(sha256(v.encode()).hexdigest() for v in (front, back))
        == (NATIVE_BUTTON_POPUP_PAIRS[key])
    )
    assert sha256(old_css.encode()).hexdigest() == NATIVE_BUTTON_POPUP_STYLE
    model = {"tmpls": [{"qfmt": front, "afmt": back}], "css": old_css}
    custom = deepcopy(model)
    custom["tmpls"][0]["afmt"] += "<p>My custom layout</p>"
    assert not upgrade_stock_layout(custom, key)
    assert upgrade_stock_layout(model, key)
    assert model["tmpls"] == [{"qfmt": spec.front, "afmt": spec.back}]
    assert model["css"] == CSS
    assert not upgrade_stock_layout(model, key)


@pytest.mark.parametrize("key", PRE_MEANINGS_PAIRS)
def test_click_only_popup_migrates_to_touch_handlers(key):
    from hashlib import sha256

    from katanki.generation.layout_fingerprints import CLICK_ONLY_POPUP_PAIRS

    spec = note_type_spec(key)
    front, back = (previous_click_layout(value) for value in (spec.front, spec.back))
    assert (
        tuple(sha256(value.encode()).hexdigest() for value in (front, back))
        == (CLICK_ONLY_POPUP_PAIRS[key])
    )
    model = {"tmpls": [{"qfmt": front, "afmt": back}], "css": CSS}
    assert upgrade_stock_layout(model, key)
    assert model["tmpls"] == [{"qfmt": spec.front, "afmt": spec.back}]


def test_source_reading_selects_matching_dictionary_meaning():
    from katanki.common.models import DiscoveryReport, KanjiEntry, NoteText
    from katanki.generation.discovery import scan_notes

    provider = WordSuggestions(
        [("今日", "きょう", 200)],
        [("今日", "きょう", ["today"]), ("今日", "こんにち", ["nowadays"])],
    )
    scan = scan_notes([NoteText(("今日",), field_readings=("こんにち",))])
    report = DiscoveryReport(scan, (KanjiEntry("日", (), (), ("day",)),), (), (), True, ())
    preview = build_preview(
        report,
        (),
        recognition=("日",),
        production=(),
        include_primitives=False,
        word_suggestions=provider,
    )
    assert preview.contents[0].example_meanings == (("今日", ("nowadays",)),)
