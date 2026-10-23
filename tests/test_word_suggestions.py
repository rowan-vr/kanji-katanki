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
from katanki.dictionaries.words import PACK, WordSuggestions, bundled_words
from katanki.generation.preview import build_preview
from katanki.generation.review import render_card_preview
from scripts.bundle_words import convert


def row(word="時間", reading="じかん", tags="★", score=200, code=None):
    content = [{"data": {"code": code}}] if code else []
    return [word, reading, tags, "", score, content, 123, ""]


def test_convert_keeps_valid_common_pairs_and_drops_unsuitable_forms(tmp_path):
    path = tmp_path / "upstream.zip"
    with ZipFile(path, "w") as archive:
        archive.writestr("index.json", json.dumps({"format": 3, "revision": "test"}))
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
    assert any(item.outcome == "unavailable" for item in preview(options=options).plan.items)


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
    assert len(json.loads(PACK.read_text(encoding="utf-8"))["words"]) == 17126


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


def test_preparation_preserves_full_export_and_repairs_tampered_copy(tmp_path, monkeypatch):
    from hashlib import sha256

    from scripts import bundle_words

    cache = tmp_path / "data/upstream"
    cache.mkdir(parents=True)
    source = cache / "jitendex-yomitan.zip"
    with ZipFile(source, "w") as archive:
        archive.writestr("index.json", json.dumps({"format": 3, "revision": "test"}))
        # Definitions and low-priority entries survive in the full archive even
        # though they are deliberately absent from the automatic suggestion index.
        archive.writestr("term_bank_1.json", json.dumps([row(), row("稀", score=0)]))
        archive.writestr("image.svg", "<svg/>")
    payload, _ = convert(source)
    (cache / "LICENSE.txt").write_text("Synthetic license", encoding="utf-8")
    lock = {
        "version": "test",
        "notice": "Synthetic notice",
        "pack_sha256": sha256(payload).hexdigest(),
        "resources": {
            name: {"sha256": sha256((cache / name).read_bytes()).hexdigest()}
            for name in (source.name, "LICENSE.txt")
        },
    }
    lock_path = tmp_path / "lock.json"
    lock_path.write_text(json.dumps(lock), encoding="utf-8")
    target = tmp_path / "pack"
    monkeypatch.setattr(bundle_words, "ROOT", tmp_path)
    monkeypatch.setattr(bundle_words, "LOCK", lock_path)
    monkeypatch.setattr(bundle_words, "TARGET", target)
    bundle_words.prepare(offline=True)
    assert (target / source.name).read_bytes() == source.read_bytes()
    assert (target / "LICENSE.txt").read_text(encoding="utf-8") == "Synthetic license"
    assert json.loads((target / "words.json").read_text(encoding="utf-8"))["words"] == [
        ["時間", "じかん", 200]
    ]
    (target / source.name).write_bytes(b"damaged export")
    bundle_words.prepare(offline=True)
    assert (target / source.name).read_bytes() == source.read_bytes()
