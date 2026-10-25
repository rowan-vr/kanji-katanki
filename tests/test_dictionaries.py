import gzip
import json
from pathlib import Path

import pytest

from katanki.common.models import ScanResult
from katanki.dictionaries.adapters.kanjidic2_xml import KanjidicXml
from katanki.dictionaries.adapters.kanjivg_svg import KanjiVgSvg
from katanki.dictionaries.adapters.xml_data import read_xml
from katanki.dictionaries.manager import DictionaryManager
from katanki.dictionaries.registry import list_datasets, read_manifest
from katanki.generation.discovery.report import classify_scan

FIXTURES = Path(__file__).parent / "fixtures"


def test_registry_loads_default_data_only_manifests():
    manifests = list_datasets()
    assert {manifest.id for manifest in manifests} == {
        "kanjidic2",
        "kanjivg",
        "jitendex",
        "school-grades",
        "joyo",
    }
    assert all(manifest.default and manifest.attribution for manifest in manifests)


@pytest.mark.parametrize(
    "change",
    [
        {"source": "http://example.org/data"},
        {"format": "execute_python"},
        {"default": "yes"},
        {"capabilities": ["strokes"]},
        {"license": {}},
        {"extra": "field"},
        {"capabilities": [{}]},
        {"compression": [{}]},
    ],
)
def test_invalid_manifests_rejected(tmp_path, change):
    path = Path(__file__).parents[1] / "src/katanki/dictionaries/manifests/kanjidic2.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw.update(change)
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        read_manifest(path)


def test_kanjidic_normalizes_japanese_readings_english_meanings_and_primary_strokes(tmp_path):
    path = tmp_path / "kanjidic2.xml.gz"
    with gzip.open(path, "wb") as stream:
        stream.write((FIXTURES / "kanjidic2.xml").read_bytes())
    provider = KanjidicXml(path)
    entry = provider.lookup_kanji("景")
    assert entry.on_readings == ("ケイ",)
    assert entry.kun_readings == ("かげ",)
    assert entry.meanings == ("fixture scenery",)
    assert entry.stroke_count == 12
    assert provider.lookup_kanji("龘") is None


def test_stroke_adapter_rebuilds_only_safe_paths_and_preserves_order(tmp_path):
    original = (FIXTURES / "kanjivg/0666f.svg").read_text(encoding="utf-8")
    path = tmp_path / "0666f.svg"
    path.write_text(
        original.replace(
            "</svg>", '<script>alert(1)</script><image href="https://example.org/x"/></svg>'
        ),
        encoding="utf-8",
    )
    provider = KanjiVgSvg(tmp_path)
    entry = provider.lookup_strokes("景")
    assert entry.components == ("日", "京")
    assert b"script" not in entry.svg and b"href" not in entry.svg
    assert entry.svg.index(b"M10,10") < entry.svg.index(b"M50,20")
    assert len(provider.hashes["景"]) == 64
    assert provider.lookup_strokes("色") is None


def test_report_does_not_call_every_cjk_character_supported():
    manager = DictionaryManager(
        {"kanjidic2": FIXTURES / "kanjidic2.xml", "kanjivg": FIXTURES / "kanjivg"}
    )
    report = classify_scan(ScanResult(2, tuple(sorted("景色龘"))), manager, manager)
    assert {entry.character for entry in report.entries} == set("景色")
    assert report.unmatched == ("龘",)
    assert [entry.character for entry in report.strokes] == ["景"]
    assert report.existing_owned is None and report.missing_owned is None
    assert "SHA-256" in " ".join(manager.source_details())


def test_without_dictionary_candidates_remain_unclassified():
    report = classify_scan(ScanResult(1, ("景",)), None, None)
    assert not report.dictionary_loaded
    assert report.entries == () and report.unmatched == ("景",)


def test_malformed_stroke_is_reported_without_losing_kanji(tmp_path):
    (tmp_path / "0666f.svg").write_text("<svg broken", encoding="utf-8")
    manager = DictionaryManager({"kanjidic2": FIXTURES / "kanjidic2.xml", "kanjivg": tmp_path})
    report = classify_scan(ScanResult(1, ("景",)), manager, manager)
    assert len(report.entries) == 1 and report.strokes == ()
    assert "Malformed XML" in report.warnings[0]


@pytest.mark.parametrize("payload", [b'<!DOCTYPE x [<!ENTITY a "x">]><x>&a;</x>', b"<x>"])
def test_invalid_xml_or_entities_are_rejected(tmp_path, payload):
    path = tmp_path / "data.xml"
    path.write_bytes(payload)
    with pytest.raises(ValueError):
        read_xml(path)


def test_expanded_gzip_size_is_bounded(tmp_path):
    path = tmp_path / "data.gz"
    with gzip.open(path, "wb") as stream:
        stream.write(b"x" * 100)
    with pytest.raises(ValueError, match="size limit"):
        read_xml(path, limit=10)
