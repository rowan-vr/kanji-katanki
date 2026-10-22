from types import SimpleNamespace

import pytest

from katanki.anki.identities import MODEL_MARKER, owned_identities
from katanki.generation.planner import Identity


def collection(models, notes):
    return SimpleNamespace(
        models=SimpleNamespace(all=lambda: models),
        find_notes=lambda query: [
            nid for nid, note in notes.items() if note["mid"] == int(query[4:])
        ],
        get_note=notes.__getitem__,
    )


def model(note_type="kanji-recognition", mid=42):
    return {
        "id": mid,
        MODEL_MARKER: note_type,
        "flds": [{"name": "Character" if note_type.startswith("kanji-") else "Component"}],
    }


def test_owned_character_detection_counts_duplicates_without_modification():
    notes = {1: {"mid": 42, "Character": "景"}, 2: {"mid": 42, "Character": "景"}}
    host = collection([model()], notes)
    assert owned_identities(host, note_type="kanji-recognition") == {
        Identity("kanji-recognition", "景"): (1, 2)
    }
    assert len(notes) == 2


def test_recognition_and_production_are_independent():
    notes = {1: {"mid": 42, "Character": "景"}, 2: {"mid": 43, "Character": "色"}}
    host = collection([model(), model("kanji-production", 43)], notes)
    assert owned_identities(host, note_type="kanji-production") == {
        Identity("kanji-production", "色"): (2,)
    }


def test_unencoded_primitive_key():
    host = collection(
        [model("primitive-recognition")], {1: {"mid": 42, "Component": "vg:shape/001"}}
    )
    assert owned_identities(host, note_type="primitive-recognition") == {
        Identity("primitive-recognition", "vg:shape/001"): (1,)
    }


def test_unowned_models_are_ignored_even_with_matching_fields():
    unowned = model()
    del unowned[MODEL_MARKER]
    host = collection([unowned], {1: {"mid": 42, "Character": "景"}})
    assert owned_identities(host, note_type="kanji-recognition") == {}


def test_invalid_owned_metadata_fails_closed():
    invalid = model()
    invalid["flds"] = []
    for models, notes in (([invalid], {}), ([model()], {1: {"mid": 42, "Character": ""}})):
        with pytest.raises(ValueError):
            owned_identities(collection(models, notes), note_type="kanji-recognition")
