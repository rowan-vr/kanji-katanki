"""Per-category destinations and tags are immutable generation preview data."""

from types import SimpleNamespace

from katanki.common.models import ComponentEntry, NoteText, StrokeEntry
from katanki.config import GenerationSettings, Settings
from katanki.generation.destinations import creation_options, generated_tags
from katanki.generation.discovery import scan_notes
from katanki.generation.planner import Identity, LearningUnit, PlanItem


def test_tag_copy_filters_match_whole_tags_and_defaults_always_apply():
    source = ("source::NIJ", "source::NIJ::lesson1", "source::Other::lesson1", "unrelated")
    preferences = GenerationSettings(
        default_tags=("katanki", "SOURCE::NIJ::lesson1"),
        copy_source_tags=True,
        source_tag_patterns=("source::NIJ::*",),
    )
    assert generated_tags(preferences, source) == ("katanki", "SOURCE::NIJ::lesson1")
    assert generated_tags(GenerationSettings(copy_source_tags=True), source) == source
    assert generated_tags(GenerationSettings(default_tags=("manual",)), source) == ("manual",)
    assert (
        generated_tags(
            GenerationSettings(copy_source_tags=True, source_tag_patterns=("NIJ",)), source
        )
        == ()
    )


def test_scans_collect_tags_only_from_notes_containing_each_character():
    scan = scan_notes(
        [
            NoteText(("景色",), ("source::NIJ::one",)),
            NoteText(("景",), ("source::Other::two",)),
            NoteText(("時間",), ("time",)),
        ]
    )
    tags = dict(scan.character_tags)
    assert tags["景"] == ("source::NIJ::one", "source::Other::two")
    assert tags["色"] == ("source::NIJ::one",)
    assert tags["時"] == ("time",)


def test_separate_destinations_and_parts_inherit_parent_kanji_tags():
    scan = scan_notes([NoteText(("景",), ("source::NIJ::one", "other"))])
    report = SimpleNamespace(scan=scan)
    report.strokes = (
        StrokeEntry(
            character="景",
            svg=b"",
            components=("日",),
            prerequisites=("日",),
            component_entries=(
                ComponentEntry("日", "sun", b"", ("shape",)),
                ComponentEntry("shape", "shape", b"", ()),
            ),
        ),
    )
    identities = (
        Identity("kanji-recognition", "景"),
        Identity("kanji-production", "景"),
        Identity("primitive-recognition", "shape"),
    )
    preview = SimpleNamespace(
        plan=SimpleNamespace(
            items=tuple(PlanItem(LearningUnit(identity), "create", "") for identity in identities)
        )
    )
    settings = Settings(
        generation=(
            GenerationSettings(True, 10, ("recognition",), True, ("source::NIJ::*",)),
            GenerationSettings(True, 20, ("production",)),
            GenerationSettings(True, 30, ("parts",), True),
        )
    )
    options = creation_options(preview, report, settings, None)
    assert [item.deck_id for item in options] == [10, 20, 30]
    assert options[0].tags == ("recognition", "source::NIJ::one")
    assert options[1].tags == ("production",)
    assert options[2].tags == ("parts", "other", "source::NIJ::one")
