from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from katanki.anki.collection import selected_notes
from katanki.common.models import NoteText, ScanSelection
from katanki.generation.discovery import extract_candidates, scan_notes


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("景色", set("景色")),
        ("少数民族", set("少数民族")),
        ("ひらがなカタカナ", set()),
        ("。！？、123", set()),
        ("景色 English カナ 𠮷 﨑 〇", set("景色𠮷﨑〇")),
        ('<img src="漢.svg" alt="字">景<script>色</script><style>少</style><!--数-->', {"景"}),
        ("&#26223;&#x8272;[sound:漢字.mp3]", set("景色")),
    ],
)
def test_candidate_extraction(text, expected):
    assert extract_candidates(text) == expected


def test_scanning_counts_notes_once_and_deduplicates_across_fields():
    report = scan_notes([NoteText(("景色景", "色")), NoteText(("少数民族",)), NoteText(("かな",))])
    assert report.scanned_notes == 3
    assert report.candidates == tuple(sorted(set("景色少数民族")))


def test_read_adapter_filters_source_and_projects_only_selected_fields():
    collection = Mock()
    collection.models.get.return_value = {"flds": [{"name": "Expression"}, {"name": "Meaning"}]}
    collection.decks.all_names_and_ids.return_value = [SimpleNamespace(id=10)]
    collection.find_notes.return_value = [3, 3, 2]
    collection.get_note.side_effect = lambda nid: {"Expression": "景色", "Meaning": "秘密"}
    result = list(selected_notes(collection, ScanSelection((10,), 20, ("Expression",))))
    assert result == [NoteText(("景色",)), NoteText(("景色",))]
    collection.find_notes.assert_called_once_with("(did:10) mid:20")
    assert collection.get_note.call_count == 2
    assert {call[0] for call in collection.mock_calls} <= {
        "models.get",
        "decks.all_names_and_ids",
        "find_notes",
        "get_note",
    }


def test_invalid_fields_fail_before_note_search():
    collection = Mock()
    collection.models.get.return_value = {"flds": [{"name": "Expression"}]}
    with pytest.raises(ValueError, match="fields no longer exist"):
        list(selected_notes(collection, ScanSelection((10,), 20, ("Removed",))))
    collection.find_notes.assert_not_called()


@pytest.mark.parametrize(
    "decks,model,fields",
    [((), 1, ("Front",)), ((1,), 1, ()), (("1 or deck:*",), 1, ("Front",)), ((1,), -1, ("Front",))],
)
def test_invalid_source_selections_are_rejected(decks, model, fields):
    with pytest.raises(ValueError):
        ScanSelection(decks, model, fields)


def test_vocabulary_examples_are_deduplicated_from_selected_fields_without_ruby_or_media():
    from katanki.generation.discovery import extract_vocabulary

    text = (
        "<div><ruby>時間<rt>じかん</rt></ruby></div><div>間</div>"
        "真ん中<br>時間[じかん] [sound:時計.mp3]"
        '<img src="秘密.svg"><script>隠す</script>'
    )
    assert extract_vocabulary(text) == {"時間", "間", "真ん中"}
    result = scan_notes([NoteText((text,)), NoteText(("時間",))])
    assert result.vocabulary == tuple(sorted(("時間", "間", "真ん中")))


def test_source_patterns_resolve_all_decks_subdecks_and_new_decks():
    from katanki.anki.collection import resolve_sources
    from katanki.config import SourceRule

    collection = Mock()
    decks = [
        SimpleNamespace(id=i, name=name)
        for i, name in enumerate(
            ["Default", "Japanese", "Japanese::Vocab", "Japanese::Vocab::Extra", "Other"], 1
        )
    ]
    collection.decks.all_names_and_ids.return_value = decks
    collection.models.all.return_value = []
    rules = (SourceRule("*", 10, ("Expression",)), SourceRule("Japanese::Vocab", 20, ("Front",)))
    selections = resolve_sources(collection, rules)
    assert selections == (
        ScanSelection((1, 2, 3, 4, 5), 10, ("Expression",)),
        ScanSelection((3, 4), 20, ("Front",)),
    )
    decks.append(SimpleNamespace(id=6, name="Japanese::New"))
    assert resolve_sources(collection, rules)[0].deck_ids == (1, 2, 3, 4, 5, 6)
    assert resolve_sources(collection, (SourceRule("Japanese::*", 20, ("Front",)),))[
        0
    ].deck_ids == (3, 4, 6)
    with pytest.raises(ValueError, match="No decks match"):
        resolve_sources(collection, (SourceRule("Absent*", 20, ("Front",)),))


def test_explicit_source_ids_survive_deck_rename_and_include_children():
    from katanki.anki.collection import resolve_sources
    from katanki.config import SourceRule

    collection = Mock()
    collection.models.all.return_value = []
    collection.decks.all_names_and_ids.return_value = [
        SimpleNamespace(id=1, name="Renamed"),
        SimpleNamespace(id=2, name="Renamed::Child"),
    ]
    assert resolve_sources(collection, (SourceRule("", 10, ("Front",), (1,)),))[0].deck_ids == (
        1,
        2,
    )
    with pytest.raises(ValueError, match="source deck is missing"):
        resolve_sources(collection, (SourceRule("", 10, ("Front",), (3,)),))


def test_overlapping_rules_count_each_note_once_and_union_selected_fields():
    collection = Mock()
    collection.models.get.return_value = {"flds": [{"name": "Front"}, {"name": "Back"}]}
    collection.decks.all_names_and_ids.return_value = [
        SimpleNamespace(id=10),
        SimpleNamespace(id=11),
    ]
    collection.find_notes.side_effect = [[1, 2, 2], [2, 3]]
    collection.get_note.side_effect = lambda nid: {"Front": f"景{nid}", "Back": "色"}
    notes = list(
        selected_notes(
            collection,
            (ScanSelection((10, 11), 20, ("Front",)), ScanSelection((11,), 20, ("Back",))),
        )
    )
    assert notes == [NoteText(("景1",)), NoteText(("景2", "色")), NoteText(("色",))]
    assert collection.get_note.call_count == 3
    assert scan_notes(notes).scanned_notes == 3


def test_invalid_later_rule_fails_before_any_search():
    collection = Mock()
    collection.models.get.return_value = {"flds": [{"name": "Front"}]}
    collection.decks.all_names_and_ids.return_value = [SimpleNamespace(id=10)]
    with pytest.raises(ValueError, match="fields no longer exist"):
        list(
            selected_notes(
                collection,
                (ScanSelection((10,), 20, ("Front",)), ScanSelection((10,), 20, ("Missing",))),
            )
        )
    collection.find_notes.assert_not_called()


@pytest.mark.parametrize(
    ("types", "expected"),
    [
        ((), "missing"),
        ((0,), "new"),
        ((1,), "learning"),
        ((2,), "learned"),
        ((3,), "relearning"),
        ((0, 2), "learned"),
    ],
)
def test_adapter_reads_card_stage_without_changing_scheduling(types, expected):
    class SourceNote(dict):
        tags = []

        def cards(self):
            return [SimpleNamespace(type=value, queue=-1) for value in types]

    collection = Mock()
    collection.models.get.return_value = {"flds": [{"name": "Expression"}]}
    collection.decks.all_names_and_ids.return_value = [SimpleNamespace(id=10)]
    collection.find_notes.return_value = [1]
    collection.get_note.return_value = SourceNote(Expression="景色")
    notes = list(selected_notes(collection, ScanSelection((10,), 20, ("Expression",))))
    assert notes == [NoteText(("景色",), word_status=expected)]
    collection.update_card.assert_not_called()
    collection.update_note.assert_not_called()


@pytest.mark.parametrize(
    ("types", "expected"),
    [((0, 1), "learning"), ((0, 3, 1), "relearning"), ((3, 2, 1), "learned")],
)
def test_duplicate_source_cards_use_requested_study_order(types, expected):
    class SourceNote(dict):
        def cards(self):
            return [SimpleNamespace(type=value) for value in types]

    collection = Mock()
    collection.models.get.return_value = {"flds": [{"name": "Expression"}]}
    collection.decks.all_names_and_ids.return_value = [SimpleNamespace(id=10)]
    collection.find_notes.return_value = [1]
    collection.get_note.return_value = SourceNote(Expression="景色")
    scan = scan_notes(selected_notes(collection, ScanSelection((10,), 20, ("Expression",))))
    assert scan.vocabulary_statuses == (("景色", expected),)


def test_duplicate_words_across_notes_keep_the_strongest_study_stage():
    scan = scan_notes(
        [
            NoteText(("時計",), word_status="new"),
            NoteText(("時計",), word_status="learning"),
            NoteText(("時計",), word_status="relearning"),
            NoteText(("時間",), word_status="relearning"),
            NoteText(("時間",), word_status="learned"),
        ]
    )
    assert dict(scan.vocabulary_statuses) == {"時計": "relearning", "時間": "learned"}
