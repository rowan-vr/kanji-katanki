"""Offline gallery content and output path boundaries."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from scripts import preview_cards


@pytest.mark.parametrize("bundled", (False, True))
def test_sample_cards_work_with_and_without_bundled_assets(tmp_path, monkeypatch, bundled):
    monkeypatch.setattr(preview_cards, "ROOT", tmp_path)
    pack = tmp_path / "words.zip"
    monkeypatch.setattr(preview_cards, "PACK", pack)
    provider = MagicMock()
    provider.__enter__.return_value.lookup_strokes.return_value = SimpleNamespace(svg=b"<svg/>")
    monkeypatch.setattr(preview_cards, "KanjiVgSvg", lambda path: provider)
    monkeypatch.setattr(
        preview_cards, "bundled_words", lambda: SimpleNamespace(lookup=lambda char: ("景品",))
    )
    if bundled:
        pack.touch()
        strokes = tmp_path / "src/katanki/dictionaries/bundled/kanjivg.zip"
        strokes.parent.mkdir(parents=True)
        strokes.touch()
    cards = list(preview_cards.sample_cards())
    assert [card.identity.note_type for card in cards] == [
        "kanji-recognition",
        "kanji-production",
        "primitive-recognition",
        "primitive-production",
    ]
    for card in cards[:2]:
        assert (card.svg == b"<svg/>") == bundled
        assert ("景品" in card.back_examples) == bundled
        assert "景品" not in card.front_examples
        assert len(card.examples) > card.example_limit
    assert all(not card.svg for card in cards[2:])


def test_gallery_contains_both_sides_and_themes_for_all_note_types(tmp_path, monkeypatch):
    monkeypatch.setattr(preview_cards, "ROOT", tmp_path)
    monkeypatch.setattr(preview_cards, "PACK", tmp_path / "missing.zip")
    markup = preview_cards.gallery()
    assert markup.count("<iframe ") == 16
    for kind in ("kanji", "primitive"):
        for mode in ("recognition", "production"):
            for side in ("Front", "Back"):
                for theme in ("Light", "Dark"):
                    assert f"{kind}-{mode} · {side} · {theme}" in markup
    assert "&lt;!doctype html&gt;" in markup
    assert "&lt;body class=&quot;card nightMode&quot;&gt;" in markup


def test_cli_writes_utf8_gallery_under_dist(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(preview_cards, "ROOT", tmp_path)
    monkeypatch.setattr(preview_cards, "gallery", lambda: "<h1>景</h1>")
    preview_cards.main([])
    output = tmp_path / "dist/katanki-card-layout-preview.html"
    assert output.read_text(encoding="utf-8") == "<h1>景</h1>"
    assert capsys.readouterr().out.strip() == str(output)
    preview_cards.main(["--output", "nested/preview.html"])
    assert (tmp_path / "dist/nested/preview.html").read_text(encoding="utf-8") == "<h1>景</h1>"


@pytest.mark.parametrize("output", ("../outside.html", "../../outside.html", "/outside.html"))
def test_cli_rejects_output_outside_dist(tmp_path, monkeypatch, capsys, output):
    monkeypatch.setattr(preview_cards, "ROOT", tmp_path)
    with pytest.raises(SystemExit) as error:
        preview_cards.main(["--output", output])
    assert error.value.code == 2
    assert "must be inside" in capsys.readouterr().err
    assert not list(tmp_path.rglob("*.html"))


def test_output_cannot_follow_a_symlink_outside_dist(tmp_path, monkeypatch):
    monkeypatch.setattr(preview_cards, "ROOT", tmp_path)
    (tmp_path / "dist").mkdir()
    outside = tmp_path / "outside.html"
    outside.write_text("original", encoding="utf-8")
    try:
        (tmp_path / "dist/link.html").symlink_to(outside)
    except OSError:
        pytest.skip("Creating symlinks requires privileges on this platform")
    with pytest.raises(ValueError, match="must be inside"):
        preview_cards.write_gallery(Path("link.html"))
    assert outside.read_text(encoding="utf-8") == "original"
