"""Tappable components: embedded meanings, related kanji, layout upgrade and popup script."""

import shutil
import subprocess
from hashlib import sha256

import pytest

from katanki.common.models import KanjiEntry, ScanResult, StrokeEntry
from katanki.dictionaries.words import WordSuggestions
from katanki.generation.cards import CSS, note_type_spec
from katanki.generation.component_popup import CSS as COMPONENT_CSS
from katanki.generation.component_popup import SCRIPT
from katanki.generation.discovery.report import classify_scan
from katanki.generation.layout_fingerprints import (
    DEV_COMPONENT_POPUP_PAIRS,
    DEV_COMPONENT_POPUP_STYLE,
    PRE_COMPONENT_POPUP_PAIRS,
    PRE_COMPONENT_POPUP_STYLE,
)
from katanki.generation.preview import build_preview
from katanki.generation.template_updates import upgrade_stock_layout

ENTRIES = {
    "海": KanjiEntry("海", (), (), ("sea", "ocean"), 9, 2),
    "池": KanjiEntry("池", (), (), ("pond", "cistern", "pool", "reservoir"), 6, 2),
    "泳": KanjiEntry("泳", (), (), ("swim",), 8, 3),
    "母": KanjiEntry("母", (), (), ("mama", "mother"), 5, 2),
}
COMPONENTS = {
    "海": ("氵", "毎", "母"),
    "池": ("氵", "也"),
    "泳": ("氵", "永"),
    "母": (),
}


# Dictionary-only kanji: not in the user's decks.
DICTIONARY = {
    "河": KanjiEntry("河", (), (), ("river",), 8, 5),
    "湖": KanjiEntry("湖", (), (), ("lake",), 12, 3),
    "沙": KanjiEntry("沙", (), (), (), 7, None),  # No meaning: never listed.
}


class Provider:
    radicals = {"氵": KanjiEntry("氵", (), (), ("water", "water radical (no. 85)"))}

    def lookup_kanji(self, character):
        return ENTRIES.get(character) or DICTIONARY.get(character) or self.radicals.get(character)

    def lookup_strokes(self, character):
        return StrokeEntry(character, b"", COMPONENTS[character])

    def component_index(self):
        return {"氵": ("沙", "河", "泳", "池", "海", "湖"), "母": ("海",)}


def report():
    scan = ScanResult(1, tuple(ENTRIES), ())
    return classify_scan(scan, Provider(), Provider())


def card(key="海", **kwargs):
    preview = build_preview(
        report(),
        (),
        recognition=(key,),
        production=(),
        include_primitives=False,
        word_suggestions=WordSuggestions(()),
        **kwargs,
    )
    return preview.contents[0]


def test_discovery_looks_up_components_that_are_not_discovered_kanji():
    assert [entry.character for entry in report().component_entries] == ["氵"]


def test_components_embed_meaning_and_other_kanji_that_use_them():
    content = card()
    details = {key: rest for key, *rest in content.component_details}
    # Simpler kanji first (grade, then strokes); the card's own kanji is excluded.
    # Dictionary kanji follow the user's own, without repeats or meaningless entries.
    assert details["氵"] == [
        "water, water radical (no. 85)",
        (("池", "pond, cistern, pool"), ("泳", "swim")),
        (("湖", "lake"), ("河", "river")),
    ]
    # Components that are discovered kanji use their own dictionary entry.
    assert details["母"] == ["mama, mother", (), ()]
    assert "毎" not in details  # No dictionary meaning and no other users.
    html = content.fields()["Components"]
    assert html.startswith(
        '<span data-meaning="water, water radical (no. 85)" '
        'data-kanji="池\tpond, cistern, pool\n泳\tswim" data-more="湖\tlake\n河\triver">氵</span>, '
        "毎, "
    )


def test_dictionary_kanji_can_be_turned_off():
    from katanki.config import CardSettings

    options = CardSettings(component_dictionary_kanji=False)
    content = card(card_settings={"recognition": options})
    details = {key: rest for key, *rest in content.component_details}
    assert details["氵"][2] == ()
    assert "data-more" not in content.fields()["Components"]


@pytest.mark.parametrize(("limit", "own", "more"), [(3, 2, 1), (1, 1, 0), (0, 2, 2)])
def test_dictionary_kanji_only_fill_the_remaining_limit(limit, own, more):
    from katanki.config import CardSettings

    content = card(card_settings={"recognition": CardSettings(component_kanji_limit=limit)})
    details = {key: rest for key, *rest in content.component_details}
    assert (len(details["氵"][1]), len(details["氵"][2])) == (own, more)


def test_dictionary_kanji_are_capped_when_listing_all(monkeypatch):
    from katanki.config import CardSettings
    from katanki.generation import preview

    monkeypatch.setattr(preview, "DICTIONARY_KANJI_CAP", 1)
    content = card(card_settings={"recognition": CardSettings(component_kanji_limit=0)})
    details = {key: rest for key, *rest in content.component_details}
    assert details["氵"][2] == (("湖", "lake"),)


def test_kanjivg_component_index_scans_canonical_files(tmp_path):
    from katanki.dictionaries.adapters.kanjivg_svg import KanjiVgSvg

    def svg(character, *elements):
        groups = "".join(f'<g kvg:element="{e}"/>' for e in elements)
        return f'<svg><g kvg:element="{character}">{groups}</g></svg>'

    (tmp_path / f"{ord('海'):05x}.svg").write_text(svg("海", "氵", "毎", "母"), "utf-8")
    (tmp_path / f"{ord('池'):05x}.svg").write_text(svg("池", "氵", "也"), "utf-8")
    (tmp_path / f"{ord('池'):05x}-Kaisho.svg").write_text(svg("池", "冫"), "utf-8")
    index = KanjiVgSvg(tmp_path).component_index()
    assert index["氵"] == ("池", "海")
    assert index["母"] == ("海",)
    assert "冫" not in index and "海" not in index


@pytest.mark.parametrize(("limit", "expected"), [(1, ("池",)), (0, ("池", "泳"))])
def test_component_kanji_limit_comes_from_card_settings(limit, expected):
    from katanki.config import CardSettings

    content = card(card_settings={"recognition": CardSettings(component_kanji_limit=limit)})
    details = {key: kanji for key, _, kanji, _ in content.component_details}
    assert tuple(character for character, _ in details["氵"]) == expected


def test_component_kanji_limit_defaults_to_ten():
    from katanki.common.models import KanjiEntry as Entry

    extra = {chr(0x6C60 + i): Entry(chr(0x6C60 + i), (), (), ("x",), 6, 2) for i in range(1, 13)}
    base = report()
    scan = ScanResult(1, (*base.scan.candidates, *extra), ())
    strokes = base.strokes + tuple(StrokeEntry(c, b"", ("氵",)) for c in extra)
    from dataclasses import replace

    big = replace(base, scan=scan, entries=base.entries + tuple(extra.values()), strokes=strokes)
    preview = build_preview(
        big,
        (),
        recognition=("海",),
        production=(),
        include_primitives=False,
        word_suggestions=WordSuggestions(()),
    )
    details = {key: kanji for key, _, kanji, _ in preview.contents[0].component_details}
    assert len(details["氵"]) == 10


def test_component_details_are_escaped():
    from katanki.generation.cards import components_html

    html = components_html(("<",), (("<", 'a "b" <c>', (("&", "<d>"),)),))
    assert html == (
        '<span data-meaning="a &quot;b&quot; &lt;c&gt;" data-kanji="&amp;\t&lt;d&gt;">&lt;</span>'
    )


def test_components_without_details_keep_plain_text():
    from dataclasses import replace

    content = replace(card(), component_details=())
    assert content.fields()["Components"] == "氵, 毎, 母"
    assert replace(content, components=()).fields()["Components"] == "none listed"


@pytest.mark.parametrize("key", PRE_COMPONENT_POPUP_PAIRS)
def test_previous_stock_layout_upgrades_to_component_popup(key):
    spec = note_type_spec(key)
    front, back = spec.front, spec.back.replace(SCRIPT + "\n", "", 1)
    old_css = CSS.removesuffix(COMPONENT_CSS)
    assert (sha256(front.encode()).hexdigest(), sha256(back.encode()).hexdigest()) == (
        PRE_COMPONENT_POPUP_PAIRS[key]
    )
    assert sha256(old_css.encode()).hexdigest() == PRE_COMPONENT_POPUP_STYLE
    model = {"tmpls": [{"qfmt": front, "afmt": back}], "css": old_css}
    assert upgrade_stock_layout(model, key)
    assert model["tmpls"] == [{"qfmt": spec.front, "afmt": spec.back}]
    assert model["css"] == CSS


@pytest.mark.parametrize("key", DEV_COMPONENT_POPUP_PAIRS)
def test_development_component_popup_layout_upgrades(key, monkeypatch):
    from types import SimpleNamespace

    from katanki.generation import template_updates

    front_hash, back_hash = DEV_COMPONENT_POPUP_PAIRS[key]
    hashes = {
        b"dev front": front_hash,
        b"dev back": back_hash,
        b"dev css": DEV_COMPONENT_POPUP_STYLE,
    }
    real = template_updates.sha256
    monkeypatch.setattr(
        template_updates,
        "sha256",
        lambda value: (
            SimpleNamespace(hexdigest=lambda: hashes[value]) if value in hashes else real(value)
        ),
    )
    model = {"tmpls": [{"qfmt": "dev front", "afmt": "dev back"}], "css": "dev css"}
    assert upgrade_stock_layout(model, key)
    spec = note_type_spec(key)
    assert model == {"tmpls": [{"qfmt": spec.front, "afmt": spec.back}], "css": CSS}


HARNESS = r"""
var focused;
class Element {
  constructor(tag) { this.tagName = tag; this.children = []; this.childNodes = [];
    this.style = {}; this.attrs = {}; this.events = {}; this.dataset = {};
    this.className = ''; this.nodeType = 1; this.offsetWidth = 380;
    this.offsetHeight = 200; this._text = ''; }
  get textContent() {
    return this.childNodes.length
      ? this.childNodes.map(function(n) { return n.textContent; }).join('') : this._text;
  }
  set textContent(value) { this._text = value; this.children = []; this.childNodes = []; }
  appendChild(child) { this.children.push(child); this.childNodes.push(child); }
  setAttribute(k, v) { this.attrs[k] = v; }
  addEventListener(k, fn) { this.events[k] = fn; }
  focus() { focused = this; }
  getBoundingClientRect() { return {left: 950, bottom: 760}; }
}
function text(value) { return {nodeType: 3, textContent: value}; }
function span(key, meaning, kanji, more) {
  var node = new Element('span');
  node.dataset = {meaning: meaning, kanji: kanji};
  if (more) node.dataset.more = more;
  node.appendChild(text(key));
  return node;
}
var document = {createElement: function(tag) { return new Element(tag); }};
var window = {innerWidth: 1000, innerHeight: 800};
var box = new Element('div');
box.className = 'components';
box.appendChild(span('氵', 'water', '池\tpond\n<b>\t<script>x</script>', '河\triver'));
box.appendChild(text(', kanjivg:part, '));
box.appendChild(span('毎', '', ''));
box.querySelector = function() { return true; };
var card = new Element('article');
card.querySelector = function() { return box; };
document.currentScript = {closest: function() { return card; }};
SCRIPT
var chips = box.children;
if (chips.map(function(c) { return c.textContent; }).join('|') !== '氵|kanjivg:part|毎')
  throw Error('chips ' + chips.map(function(c) { return c.textContent; }));
if (chips[1].attrs.role || !chips[0].className.includes('word-definition'))
  throw Error('only detailed components are interactive');
var overlay = card.children[0], popup = overlay.children[0];
var heading = popup.children[1], meaning = popup.children[2];
var label = popup.children[3], list = popup.children[4];
var moreLabel = popup.children[5], moreList = popup.children[6];
chips[0].onclick({preventDefault() {}, stopPropagation() {}});
if (overlay.hidden || heading.textContent !== '氵' || meaning.textContent !== 'water')
  throw Error('not opened');
if (label.textContent !== 'Used in 2 of your kanji') throw Error('label ' + label.textContent);
var row = list.children[1];
if (row.children[0].textContent !== '<b>' || row.children[1].textContent !== '<script>x</script>')
  throw Error('kanji rows must be rendered as text');
if (moreLabel.hidden || moreList.hidden || moreList.children[0].children[0].textContent !== '河')
  throw Error('dictionary kanji');
if (focused !== popup.children[0] || chips[0].attrs['aria-expanded'] !== 'true')
  throw Error('focus');
overlay.events.keydown({key: 'Escape', preventDefault() {}, stopPropagation() {}});
if (!overlay.hidden || focused !== chips[0]) throw Error('dismissal');
chips[2].events.keydown({key: 'Enter', preventDefault() {}, stopPropagation() {}});
if (meaning.textContent !== 'Meaning unavailable.' || list.children.length
    || label.textContent !== 'Not used in your other discovered kanji') throw Error('fallback');
if (!moreLabel.hidden || !moreList.hidden || moreList.children.length)
  throw Error('empty dictionary list must be hidden');
"""


def test_component_popup_script_renders_chips_and_details():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is not installed")
    script = HARNESS.replace("SCRIPT", SCRIPT.removeprefix("<script>").removesuffix("</script>"))
    result = subprocess.run([node], input=script, encoding="utf-8", capture_output=True)
    assert result.returncode == 0, result.stderr
