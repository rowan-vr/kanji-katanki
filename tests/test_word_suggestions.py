"""Jitendex conversion and offline suggestions use synthetic, network-free inputs."""

import json
from dataclasses import replace
from zipfile import ZipFile

import pytest

from katanki.common.models import (
    ComponentEntry,
    DiscoveryReport,
    KanjiEntry,
    ScanResult,
    StrokeEntry,
)
from katanki.config import CardSettings
from katanki.dictionaries.adapters.jitendex_yomitan import convert
from katanki.dictionaries.words import PACK, WordSuggestions, bundled_words
from katanki.generation.preview import build_preview
from katanki.generation.review import render_card_preview


def row(word="時間", reading="じかん", tags="★", score=200, code=None):
    content = [{"data": {"code": code}}] if code else []
    return [word, reading, tags, "", score, content, 123, ""]


def test_convert_keeps_valid_common_pairs_and_drops_unsuitable_forms(tmp_path):
    path = tmp_path / "upstream.zip"
    with ZipFile(path, "w") as archive:
        archive.writestr(
            "index.json",
            json.dumps({"format": 3, "revision": "test", "title": "Synthetic Jitendex"}),
        )
        archive.writestr(
            "term_bank_1.json",
            json.dumps(
                [
                    row(),
                    row("時間", "とき", score=99),
                    row("かな"),
                    row(tags=""),
                    row(tags="★ rarely\u00a0used\u00a0form"),
                    row(code="uk"),
                    row(code="arch"),
                ]
            ),
        )
    payload, _ = convert(path)
    assert json.loads(payload)["words"] == [["時間", "じかん", 200]]
    assert convert(path)[0] == payload


def discovery():
    return DiscoveryReport(
        ScanResult(1, ("時", "間"), ("時間割",)),
        (KanjiEntry("時", (), (), ("time",)), KanjiEntry("間", (), (), ("interval",))),
        (),
        (),
        True,
        (),
    )


def preview(report=None, options=None, **kwargs):
    return build_preview(
        report or discovery(),
        (),
        recognition=("時",),
        production=("時",),
        include_primitives=False,
        card_settings=options,
        word_suggestions=WordSuggestions(
            [
                ("時間", "じかん", 200),
                ("時計", "とけい", 100),
                ("時間割", "じかんわり", 200),
            ]
        ),
        **kwargs,
    )


def test_defaults_are_opt_in_and_follow_source_words():
    assert all(content.examples == ("時間割",) for content in preview().contents)
    options = {
        mode: CardSettings(example_source="discovered_and_default", example_limit=1)
        for mode in ("recognition", "production")
    }
    result = preview(options=options)
    for content in result.contents:
        assert content.examples == ("時間割", "時間", "時計")
        assert "時計" in content.fields()["VocabExamples"]  # Store beyond the display limit.
        assert 'data-source="vocabulary"' in content.fields()["VocabExamples"]
        assert 'data-source="default"' in content.fields()["VocabExamples"]
        assert "Jitendex" in content.fields()["Attribution"]
        front, back = render_card_preview(content)
        assert "katanki-examples" in back
        assert "{{" not in front + back
        if content.identity.note_type.endswith("production"):
            assert content.prompt == "time\n\n__間割"


def test_all_limit_and_hidden_examples_preserve_storage():
    options = {"production": CardSettings(example_source="discovered_and_default", example_limit=0)}
    result = preview(options=options)
    content = next(c for c in result.contents if c.identity.note_type.endswith("production"))
    assert content.prompt == "time\n\n__間割\n__間\n__計"
    hidden = replace(content, show_examples=False)
    assert hidden.fields()["VocabExamples"] == content.fields()["VocabExamples"]
    assert hidden.fields()["ExampleLimit"] == "-1"
    options["production"] = replace(options["production"], show_examples=False)
    result = preview(options=options)
    assert all(item.outcome == "create" for item in result.plan.items)
    production = next(c for c in result.contents if c.identity.note_type.endswith("production"))
    assert production.prompt == "time"
    assert production.examples == content.examples


def test_part_suggestions_use_containing_kanji():
    part = ComponentEntry("日", "日", b"<svg/>")
    report = replace(discovery(), strokes=(StrokeEntry("時", b"<svg/>", ("日",), (part,)),))
    result = preview(report, primitive_recognition=("日",))
    content = next(c for c in result.contents if c.identity.key == "日")
    assert content.examples == ("時",)


def test_priority_then_shorter_words_and_stable_deduplication():
    words = WordSuggestions(
        [("時間", "じかん", 100), ("時", "とき", 100), ("時代", "じだい", 200), ("時", "じ", 100)]
    )
    assert words.lookup("時") == ("時代", "時", "時間")


@pytest.mark.skipif(not PACK.is_file(), reason="Prepare the pinned word pack first")
def test_real_pack_is_offline_and_has_known_words():
    assert "時間" in bundled_words().lookup("時")
    assert "景色" in bundled_words().lookup("景")
    assert "大丈夫" in bundled_words().lookup("丈")
    assert len(json.loads(convert(PACK)[0])["words"]) == 17616


def test_production_ambiguity_is_checked_after_limiting():
    report = replace(
        discovery(),
        scan=ScanResult(0, ("時", "間")),
        entries=(
            KanjiEntry("時", (), (), ("same meaning",)),
            KanjiEntry("間", (), (), ("same meaning",)),
        ),
    )
    words = WordSuggestions(
        [("時時", "a", 200), ("間間", "b", 200), ("時計", "c", 100), ("間隔", "d", 100)]
    )
    options = {"production": CardSettings(example_source="discovered_and_default", example_limit=1)}
    result = build_preview(
        report,
        (),
        recognition=(),
        production=("時", "間"),
        include_primitives=False,
        card_settings=options,
        word_suggestions=words,
    )
    assert all(item.outcome == "unavailable" for item in result.plan.items)
    options["production"] = replace(options["production"], example_limit=0)
    result = build_preview(
        report,
        (),
        recognition=(),
        production=("時", "間"),
        include_primitives=False,
        card_settings=options,
        word_suggestions=words,
    )
    assert all(item.outcome == "create" for item in result.plan.items)


def test_preparation_preserves_full_export_and_its_attribution(tmp_path):
    from scripts.bundle_datasets import write_jitendex

    source, target = tmp_path / "upstream.zip", tmp_path / "jitendex.zip"
    notices = tmp_path / "licenses"
    notices.mkdir()
    with ZipFile(source, "w") as archive:
        archive.writestr(
            "index.json",
            json.dumps(
                {
                    "format": 3,
                    "revision": "test",
                    "title": "Synthetic Jitendex",
                    "attribution": "Original attribution",
                }
            ),
        )
        archive.writestr("term_bank_1.json", json.dumps([row(), row("稀", score=0)]))
        archive.writestr("image.svg", "<svg/>")
    assert write_jitendex(source, target, notices) == ("test", 2)
    assert target.read_bytes() == source.read_bytes()
    assert "Original attribution" in (notices / "Jitendex-Attribution.txt").read_text()


def _sense(code=None, *, example_code=None):
    content = []
    if code:
        content.append({"tag": "span", "data": {"code": code, "content": "misc-info"}})
    content.append(
        {
            "tag": "ul",
            "data": {"content": "glossary"},
            "content": [{"tag": "li", "content": "Synthetic meaning"}],
        }
    )
    if example_code:
        content.append(
            {
                "tag": "div",
                "data": {"content": "extra-info"},
                "content": {"tag": "span", "data": {"code": example_code}},
            }
        )
    return {"tag": "div", "data": {"content": "sense"}, "content": content}


def _group(*senses, code=None):
    content = list(senses)
    if code:
        content.insert(0, {"tag": "span", "data": {"code": code, "content": "misc-info"}})
    return {"tag": "li", "data": {"content": "sense-group"}, "content": content}


@pytest.mark.parametrize(
    ("groups", "expected"),
    [
        ([_group(_sense()), _group(_sense(), code="arch")], True),
        ([_group(_sense("arch"), _sense())], True),
        ([_group(_sense("arch")), _group(_sense("obs"))], False),
        ([_group(_sense(), code="uk")], False),
        ([_group(_sense(example_code="arch"))], True),
    ],
)
def test_sense_usage_tags_do_not_discard_unrelated_modern_meanings(groups, expected):
    from katanki.dictionaries.adapters.jitendex_yomitan import eligible

    entry = row("大丈夫", "だいじょうぶ")
    entry[5] = [
        {
            "type": "structured-content",
            "content": {
                "tag": "ul",
                "data": {"content": "sense-groups"},
                "content": groups,
            },
        }
    ]
    assert eligible(entry) == expected
    # Actual rare spelling forms stay excluded even when their senses are modern.
    entry[2] = "★ rarely used form"
    assert not eligible(entry)


def test_modern_sense_retained_through_conversion_and_default_word_generation(tmp_path):
    entry = row("大丈夫", "だいじょうぶ")
    entry[5] = [
        {
            "type": "structured-content",
            "content": {
                "tag": "ul",
                "data": {"content": "sense-groups"},
                "content": [_group(_sense()), _group(_sense(), code="arch")],
            },
        }
    ]
    path = tmp_path / "mixed-senses.zip"
    with ZipFile(path, "w") as archive:
        archive.writestr(
            "index.json",
            json.dumps(
                {
                    "format": 3,
                    "revision": "test",
                    "title": "Synthetic mixed senses",
                }
            ),
        )
        archive.writestr("term_bank_1.json", json.dumps([entry], ensure_ascii=False))
    payload, _ = convert(path)
    assert WordSuggestions(json.loads(payload)["words"]).lookup("丈") == ("大丈夫",)
