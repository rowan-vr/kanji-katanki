from types import SimpleNamespace

import pytest

from katanki.anki.identities import MODEL_MARKER
from katanki.anki.statistics import character_details, read_progress
from katanki.stats.progress import CardEvidence, ProgressSnapshot, card_state


def evidence(char="日", mode="recognition", state="mature", cid=1):
    return CardEvidence(char, mode, cid, cid, state, 30, 4, 0)


def test_unique_counts_mixed_duplicates_and_independent_writing():
    snapshot = ProgressSnapshot(
        (
            evidence(),
            evidence(cid=2, state="relearning"),
            evidence("月", state="young", cid=3),
            evidence("月", "writing", "mature", cid=4),
        )
    )
    result = snapshot.payload(("日", "月", "火", "日"))
    assert len(result["rows"]) == 3
    assert result["counts"]["recognition"]["relearning"] == 1
    assert result["counts"]["writing"]["missing"] == 2
    assert result["counts"]["writing"]["mature"] == 1
    assert sum(result["counts"]["recognition"].values()) == 3
    assert snapshot.state("日", "writing") == "missing"
    assert len(snapshot.details("日")["recognition"]["cards"]) == 2


@pytest.mark.parametrize(
    "kind,interval,expected",
    [
        (0, 100, "new"),
        (1, 100, "learning"),
        (2, 20, "young"),
        (2, 21, "mature"),
        (3, 100, "relearning"),
    ],
)
def test_native_type_and_maturity_boundary(kind, interval, expected):
    assert card_state(kind, interval) == expected


def test_unknown_card_types_are_not_claimed_as_learning_evidence():
    with pytest.raises(ValueError):
        card_state(99, 100)


def test_new_duplicate_prevents_claiming_maturity():
    snapshot = ProgressSnapshot((evidence(), evidence(state="new", cid=2)))
    assert snapshot.state("日", "recognition") == "new"


def test_owned_note_evidence_and_temporary_queues_without_collection_writes():
    models = [
        {
            "id": 1,
            "name": "Recognition",
            MODEL_MARKER: "kanji-recognition",
            "flds": [{"name": "Character"}],
        },
        {
            "id": 2,
            "name": "Writing",
            MODEL_MARKER: "kanji-production",
            "flds": [{"name": "Character"}],
        },
        {"id": 3, "name": "Vocab", "flds": [{"name": "Character"}]},
    ]
    cards = [
        SimpleNamespace(id=1, type=2, ivl=21, queue=-1, reps=4, lapses=0),
        SimpleNamespace(id=2, type=3, ivl=30, queue=-2, reps=5, lapses=1),
    ]

    class Note(dict):
        def cards(self):
            return self["cards"]

    notes = {10: Note(Character="日", cards=cards), 20: Note(Character="月", cards=[])}
    collection = SimpleNamespace(
        models=SimpleNamespace(all=lambda: models),
        find_notes=lambda query: {"mid:1": [10, 10], "mid:2": [20]}[query],
        get_note=notes.__getitem__,
    )
    result = read_progress(collection)
    assert len(result.cards) == 2
    assert result.state("日", "recognition") == "relearning"
    assert result.cards[0].suspended and result.cards[1].buried
    assert result.details("月")["writing"]["note_ids"] == [20]
    assert result.details("月")["writing"]["cards"] == []


def test_detail_review_totals_exclude_manual_reschedules(monkeypatch):
    monkeypatch.setattr(
        "katanki.anki.statistics.load_settings", lambda _: SimpleNamespace(dictionaries=())
    )
    monkeypatch.setattr("katanki.anki.statistics.dictionary_sources", lambda *args, **kwargs: {})
    col = SimpleNamespace(
        get_review_logs=lambda cid: [SimpleNamespace(button_chosen=i) for i in (0, 1, 3, 4)]
    )
    details = character_details(col, ProgressSnapshot((evidence(),)), "日")
    assert details["evidence"]["recognition"]["answered"] == 3
    assert details["evidence"]["recognition"]["passed"] == 2
    assert "dictionary" not in details and "svg" not in details


def test_dynamic_card_scope_without_target_lists_and_independent_modes():
    from katanki.stats.groups import coverage_sections
    from katanki.stats.targets import TargetRegistry

    progress = ProgressSnapshot(
        (evidence("龍"), evidence("龍", cid=2), evidence("亀", "writing", cid=3)),
        notes=(("日", "recognition", 4),),
    )
    sections = coverage_sections(TargetRegistry(()), progress)
    assert sections[0].characters == ()
    dynamic = sections[1]
    assert dynamic.key == ("@cards", None)
    assert dynamic.characters == ("龍", "亀")
    assert progress.payload(dynamic.characters)["counts"]["recognition"]["missing"] == 1
    assert coverage_sections(TargetRegistry(()), ProgressSnapshot(()))[1].characters == ()
    assert coverage_sections(TargetRegistry(()), ProgressSnapshot((evidence("亀"),)))[
        1
    ].characters == ("亀",)
