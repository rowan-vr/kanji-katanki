import json
from dataclasses import replace
from pathlib import Path

import pytest

from katanki.config import DictionaryChoice
from katanki.dictionaries.adapters.kanjidic2_xml import KanjidicXml
from katanki.dictionaries.registry import list_datasets
from katanki.generation.discovery import extract_candidates
from katanki.stats.sources import load_target_registry
from katanki.stats.targets import (
    MAX_BYTES,
    TargetRegistry,
    parse_target_list,
    read_target_list,
)
from scripts.generate_target_lists import joyo, school_grades

FIXTURES = Path(__file__).parent / "fixtures"


def example_list(list_id="user:course-1"):
    return {
        "schema_version": 1,
        "id": list_id,
        "title": "My textbook",
        "version": "edition-1",
        "kind": "textbook",
        "source": {
            "title": "Personal notes",
            "url": None,
            "revision": "edition-1",
            "license": "Private study; redistribution not established",
            "attribution": "Personal list",
            "authority": "user",
        },
        "groups": [
            {"id": "chapter-1", "title": "Chapter 1", "characters": ["日", "月"]},
            {"id": "chapter-2", "title": "Chapter 2", "characters": ["月", "火"]},
            {"id": "chapter-3", "title": "Chapter 3", "characters": []},
        ],
    }


def load(raw):
    return parse_target_list(json.dumps(raw, ensure_ascii=False).encode())


def test_roundtrip_and_ordered_unique_selection_without_dictionary_or_anki(tmp_path):
    target = load(example_list()).target_list
    assert target.characters() == ("日", "月", "火")
    assert target.characters(("chapter-2",)) == ("月", "火")
    assert target.characters(("chapter-2", "chapter-1")) == ("日", "月", "火")
    assert target.characters(()) == ()
    assert target.characters(("chapter-3",)) == ()
    path = tmp_path / "targets.json"
    path.write_text(target.to_json(), encoding="utf-8")
    assert read_target_list(path).target_list == target
    with pytest.raises(ValueError, match="Unknown group"):
        target.characters(("typo",))


def test_duplicate_members_warn_but_cross_group_overlap_is_valid():
    raw = example_list()
    raw["groups"][0]["characters"].extend(["日", "月"])
    loaded = load(raw)
    assert loaded.target_list.characters() == ("日", "月", "火")
    assert loaded.warnings == ("Group chapter-1: removed 2 duplicates.",)


def test_many_lists_can_coexist_and_union_is_stable():
    first = load(example_list()).target_list
    second = replace(first, id="user:other-course", kind="future-classification")
    registry = TargetRegistry((first, second))
    assert registry.lists == (first, second)
    assert registry.targets(((second.id, ("chapter-2",)), (first.id, ("chapter-1",)))) == (
        "月",
        "火",
        "日",
    )
    assert registry.targets(()) == ()
    with pytest.raises(ValueError, match="already registered"):
        registry.register(first)
    with pytest.raises(ValueError, match="Unknown target list"):
        registry.targets((("user:unknown", None),))


def test_exact_variants_supplementary_han_and_zero_match_discovery_policy():
    raw = example_list()
    characters = ["崎", "﨑", "𠮷", "〇", "龘"]
    raw["groups"] = [{"id": "all", "title": "All", "characters": characters}]
    target = load(raw).target_list
    assert target.characters() == tuple(characters)
    assert set(target.characters()) == extract_candidates("".join(characters))


@pytest.mark.parametrize("member", ["日本", "あ", "", "<b>日</b>", "日\ufe00", None, {}, 42])
def test_invalid_members_report_group_and_position(member):
    raw = example_list()
    raw["groups"][0]["characters"][1] = member
    with pytest.raises(ValueError, match="Group chapter-1, member 2"):
        load(raw)


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": True},
        {"schema_version": 2},
        {"id": "../../unsafe"},
        {"kind": ""},
        {"title": 1},
        {"groups": []},
        {"groups": {}},
        {"groups": [{"id": "all", "title": "Empty", "characters": []}]},
        {"groups": [{"id": "all", "title": "Not array", "characters": "日月"}]},
        {"source": None},
        {"unknown": "field"},
    ],
)
def test_invalid_contract_is_rejected(change):
    with pytest.raises(ValueError):
        load(example_list() | change)


@pytest.mark.parametrize(
    "change",
    [
        {"authority": "maybe"},
        {"authority": []},
        {"url": "http://example.org"},
        {"url": "https://user:password@example.org"},
        {"sha256": "bad"},
        {"license": ""},
        {"revision": None},
        {"unexpected": "field"},
    ],
)
def test_invalid_provenance_is_rejected(change):
    raw = example_list()
    raw["source"].update(change)
    with pytest.raises(ValueError):
        load(raw)


def test_duplicate_group_ids_and_duplicate_json_keys_fail():
    raw = example_list()
    raw["groups"].append(raw["groups"][0])
    with pytest.raises(ValueError, match="Duplicate target group"):
        load(raw)
    with pytest.raises(ValueError, match="Duplicate JSON key"):
        parse_target_list(b'{"schema_version": 1, "schema_version": 1}')
    with pytest.raises(ValueError):
        parse_target_list(b"[]")
    with pytest.raises(ValueError, match="UTF-8"):
        parse_target_list(b"\xff")


def test_import_limits_bytes_groups_and_members(tmp_path, monkeypatch):
    path = tmp_path / "large.json"
    path.write_bytes(b" " * (MAX_BYTES + 1))
    with pytest.raises(ValueError, match="size limit"):
        read_target_list(path)
    monkeypatch.setattr("katanki.stats.targets.MAX_MEMBERS", 2)
    with pytest.raises(ValueError, match="member limit"):
        load(example_list())
    monkeypatch.setattr("katanki.stats.targets.MAX_GROUPS", 2)
    with pytest.raises(ValueError, match="groups"):
        load(example_list())


def test_kanjidic_grades_exclude_name_only_and_unclassified_entries(tmp_path):
    xml = (FIXTURES / "kanjidic2.xml").read_text(encoding="utf-8")
    extra = "".join(
        f"<character><literal>{char}</literal><misc><grade>{grade}</grade></misc></character>"
        for char, grade in (("日", 1), ("亜", 8), ("凜", 9), ("﨑", 10))
    )
    path = tmp_path / "kanjidic.xml"
    path.write_text(xml.replace("</kanjidic2>", extra + "</kanjidic2>"), encoding="utf-8")
    manifest = next(item for item in list_datasets() if item.id == "kanjidic2")
    target = school_grades(KanjidicXml(path), manifest, "2026-10-24")
    assert target.id == "school-grades"
    assert target.characters() == ("日", "色", "景")
    full = joyo(KanjidicXml(path), manifest, "2026-10-24")
    assert full.characters() == tuple(sorted("日色景亜"))
    with pytest.raises(ValueError, match="Unknown group"):
        target.characters(("grade-8",))
    assert [group.id for group in target.groups] == [f"grade-{g}" for g in (1, 2, 3, 4, 5, 6)]
    assert target.source.authority == "unofficial"
    assert target.source.revision != target.version
    assert len(target.source.sha256) == 64
    assert load(json.loads(target.to_json())).target_list == target
    before = path.read_bytes()
    school_grades(KanjidicXml(path), manifest, "2026-10-24")
    assert path.read_bytes() == before


def test_empty_grade_metadata_does_not_invent_targets(tmp_path):
    path = tmp_path / "no-grades.xml"
    path.write_text(
        (FIXTURES / "kanjidic2.xml")
        .read_text(encoding="utf-8")
        .replace("<grade>4</grade>", "")
        .replace("<grade>2</grade>", ""),
        encoding="utf-8",
    )
    manifest = next(item for item in list_datasets() if item.id == "kanjidic2")
    with pytest.raises(ValueError, match="members"):
        school_grades(KanjidicXml(path), manifest, "2026-10-24")
    assert load_target_registry({"kanjidic2": path}).lists == ()


def test_saved_disabled_and_local_choices_resolve_without_other_dictionary_files(tmp_path):
    disabled = DictionaryChoice("school-grades", "disabled")
    unrelated = DictionaryChoice("jitendex", "local", "/nonexistent/unrelated.zip")
    other_list = DictionaryChoice("joyo", "disabled")
    assert load_target_registry(choices=(disabled, unrelated, other_list)).lists == ()
    path = tmp_path / "list.json"
    path.write_text(json.dumps(example_list()), encoding="utf-8")
    local = DictionaryChoice("school-grades", "local", str(path))
    registry = load_target_registry(choices=(local, unrelated, other_list))
    assert registry.lists[0].characters() == ("日", "月", "火")


def test_unknown_dataset_and_bad_compression_fail(tmp_path):
    with pytest.raises(ValueError, match="Unknown target dataset"):
        load_target_registry({"unknown": tmp_path})
    path = tmp_path / "kanjidic.zip"
    path.write_bytes(b"wrong format")
    with pytest.raises(ValueError, match="does not support zip"):
        load_target_registry({"school-grades": path})


def test_coverage_sections_preserve_groups_and_deduplicate_all_lists():
    from katanki.stats.groups import coverage_sections, normalize_search

    target = load(example_list()).target_list
    single = replace(target, id="user:single", groups=(target.groups[0],))
    sections = coverage_sections(TargetRegistry((target, single)))
    assert [section.key for section in sections] == [
        ("", None),
        (target.id, None),
        (target.id, "chapter-1"),
        (target.id, "chapter-2"),
        (target.id, "chapter-3"),
        (single.id, None),
    ]
    assert sections[0].characters == ("日", "月", "火")
    assert sections[2].parent == (target.id, None)
    assert sections[3].characters == ("月", "火")
    assert normalize_search("ｹﾞﾂ") == normalize_search("げつ")
