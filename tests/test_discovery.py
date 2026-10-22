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
