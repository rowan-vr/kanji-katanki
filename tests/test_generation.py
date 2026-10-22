"""Realistic fixture-to-plan checks; no host or network dependency."""

from dataclasses import replace
from pathlib import Path

import pytest

from katanki.common.models import (
    ComponentEntry,
    DiscoveryReport,
    KanjiEntry,
    ScanResult,
    StrokeEntry,
)
from katanki.dictionaries.adapters.kanjivg_svg import KanjiVgSvg
from katanki.dictionaries.manager import DictionaryManager
from katanki.generation.cards import note_type_spec
from katanki.generation.discovery.report import classify_scan
from katanki.generation.planner import Identity
from katanki.generation.preview import build_preview

FIXTURES = Path(__file__).parent / "fixtures"


def report():
    with DictionaryManager(
        {"kanjidic2": FIXTURES / "kanjidic2.xml", "kanjivg": FIXTURES / "kanjivg"}
    ) as manager:
        return replace(
            classify_scan(ScanResult(1, ("景", "色"), ("景色",)), manager, manager),
            attribution=manager.card_attribution(),
        )


def preview(discovery=None, **choices):
    options = dict(recognition=("景", "色"), production=(), include_primitives=False)
    options.update(choices)
    return build_preview(discovery or report(), (), **options)


def test_fixture_components_preserve_hierarchy_and_source_labels():
    with KanjiVgSvg(FIXTURES / "kanjivg") as provider:
        entry = provider.lookup_strokes("景")
    assert entry.prerequisites == ("日", "京")
    assert {component.key for component in entry.component_entries} == {"日", "京"}
    plan = preview(include_primitives=True)
    outcomes = {item.unit.identity: item.outcome for item in plan.plan.items}
    assert outcomes[Identity("kanji-recognition", "景")] == "create"
    assert outcomes[Identity("kanji-recognition", "色")] == "unavailable"
    assert len([identity for identity in outcomes if identity.kind == "primitive"]) == 2
    order = [item.unit.identity.key for item in plan.plan.items]
    assert order.index("日") < order.index("景")
    assert order.index("京") < order.index("景")


def test_unnamed_nested_and_split_components_are_stable_and_sanitized(tmp_path):
    svg = """<svg xmlns="http://www.w3.org/2000/svg" xmlns:k="http://kanjivg.tagaini.net">
    <g k:element="景"><g id="shape"><g k:element="日"><path d="M1,2 L3,4"/></g></g>
    <g k:element="日"><path d="M5,6 L7,8"/></g><g><path d="M9,0 L1,2"/></g></g>
    <script>bad()</script></svg>"""
    (tmp_path / "0666f.svg").write_text(svg, encoding="utf-8")
    with KanjiVgSvg(tmp_path) as provider:
        first = provider.lookup_strokes("景")
        assert provider.lookup_strokes("景") == first
    components = {component.key: component for component in first.component_entries}
    shape = components["kanjivg:0666f:shape"]
    assert shape.prerequisites == ("日",)
    assert components["日"].svg.count(b"<path") == 2
    assert any(key.startswith("kanjivg:paths:") for key in components)
    assert all(b"script" not in component.svg for component in components.values())
    result = preview(
        replace(report(), strokes=(first,)), recognition=("景",), include_primitives=True
    )
    assert result.plan.items[-1].outcome == "unavailable"  # Unnamed prerequisite needs a name.


def test_optional_production_and_missing_diagram_fallback():
    result = preview(production=("景",))
    assert len(result.plan.items) == 3
    assert all(item.outcome == "create" for item in result.plan.items)
    assert Identity("kanji-production", "色") not in {
        item.unit.identity for item in result.plan.items
    }
    fields = next(content.fields() for content in result.contents if content.identity.key == "色")
    assert fields["Strokes"] == "Stroke data unavailable"
    assert "KanjiVG" in fields["Attribution"]
    assert str(FIXTURES) not in fields["Attribution"]


def test_production_without_meaning_or_source_examples_is_unavailable():
    for discovery in (
        replace(report(), scan=ScanResult(1, ("景", "色"))),
        replace(report(), entries=(KanjiEntry("景", (), (), ()),)),
    ):
        result = preview(discovery, recognition=(), production=("景",))
        assert result.plan.items[0].outcome == "unavailable"


def test_dictionary_text_and_prompts_are_escaped():
    discovery = replace(report(), entries=(KanjiEntry("景", (), (), ("<script>bad()</script>",)),))
    result = preview(discovery, recognition=(), production=("景",))
    fields = result.contents[0].fields()
    assert fields["Prompt"] == "&lt;script&gt;bad()&lt;/script&gt;<br><br>__色"
    assert "<script>" not in fields["Meanings"]
    for mode in ("recognition", "production"):
        spec = note_type_spec(f"kanji-{mode}")
        assert "KatankiIdentity" not in spec.fields
        assert spec.fields[0] == "Character"
        assert "katankiPlay" in spec.back
        assert "katankiNumbers" in spec.back
    assert "{{Prompt}}" in note_type_spec("kanji-production").front
    assert "{{Display}}" not in note_type_spec("kanji-production").front


def test_missing_components_and_cycles_never_produce_a_valid_creation_plan():
    discovery = DiscoveryReport(
        ScanResult(1, ("景",)),
        (KanjiEntry("景", (), (), ()),),
        (StrokeEntry("景", b"", (), (), ("missing",)),),
        (),
        True,
        (),
    )
    assert all(
        item.outcome == "unavailable"
        for item in preview(discovery, recognition=("景",), include_primitives=True).plan.items
    )
    cyclic = replace(
        discovery,
        strokes=(
            StrokeEntry(
                "景",
                b"",
                (),
                (
                    ComponentEntry("日", "日", b"", ("京",)),
                    ComponentEntry("京", "京", b"", ("日",)),
                ),
                ("日",),
            ),
        ),
    )
    with pytest.raises(ValueError, match="cycle"):
        preview(cyclic, recognition=("景",), include_primitives=True)


def test_explicit_unnamed_component_names_and_independent_primitive_production():
    component = ComponentEntry("vg:shape", "Unencoded graphical component", b"<svg/>")
    discovery = replace(
        report(),
        strokes=(StrokeEntry("景", b"<svg/>", (), (component,), ("vg:shape",)),),
    )
    result = preview(
        discovery,
        recognition=(),
        component_names={"vg:shape": "little roof"},
        primitive_production=("vg:shape",),
    )
    assert len(result.plan.items) == 1
    item = result.plan.items[0]
    assert item.outcome == "create"
    assert item.unit.identity == Identity("primitive-production", "vg:shape")
    assert result.contents[0].display == "little roof"
    assert result.contents[0].fields()["Component"] == "vg:shape"
    result = preview(
        discovery,
        recognition=("景",),
        include_primitives=True,
        component_names={"vg:shape": "little roof"},
    )
    assert all(item.outcome == "create" for item in result.plan.items)
    assert Identity("primitive-production", "vg:shape") not in {
        item.unit.identity for item in result.plan.items
    }


def test_user_vocabulary_examples_mask_only_the_asked_kanji():
    from katanki.common.models import NoteText
    from katanki.generation.discovery import scan_notes

    scan = scan_notes([NoteText((word,)) for word in ("時間", "間", "真ん中", "時間")])
    discovery = DiscoveryReport(
        scan,
        (KanjiEntry("時", (), (), ("time",)), KanjiEntry("間", (), (), ("interval",))),
        (),
        (),
        True,
        (),
    )
    result = preview(discovery, recognition=(), production=("時", "間"))
    by_key = {content.identity.key: content for content in result.contents}
    assert by_key["時"].prompt == "time\n\n__間"
    assert by_key["時"].examples == ("時間",)
    assert by_key["間"].prompt == "interval\n\n時__\n__"
    assert by_key["間"].examples == ("時間", "間")
    assert "真ん中" not in by_key["間"].prompt
    assert by_key["時"].fields()["Prompt"] == "time<br><br>__間"


def test_vocabulary_snapshot_survives_source_removal_and_masks_repeated_characters():
    from katanki.common.models import NoteText
    from katanki.generation.discovery import scan_notes

    notes = [NoteText(("時々時",))]
    scan = scan_notes(notes)
    notes.clear()
    discovery = replace(report(), scan=scan, entries=(KanjiEntry("時", (), (), ("time",)),))
    result = preview(discovery, recognition=(), production=("時",))
    assert result.contents[0].prompt == "time\n\n__々__"
    assert scan.vocabulary == ("時々時",)


def test_identical_automatic_clues_are_unavailable_until_source_words_disambiguate():
    discovery = replace(
        report(),
        scan=ScanResult(2, ("時", "刻"), ("時", "刻")),
        entries=(KanjiEntry("時", (), (), ("time",)), KanjiEntry("刻", (), (), ("time",))),
    )
    result = preview(discovery, recognition=(), production=("時", "刻"))
    assert all(item.outcome == "unavailable" for item in result.plan.items)
    discovery = replace(discovery, scan=replace(discovery.scan, vocabulary=("時間", "時", "刻")))
    assert all(
        item.outcome == "create"
        for item in preview(discovery, recognition=(), production=("時", "刻")).plan.items
    )
