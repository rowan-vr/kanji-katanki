"""Parts keys and evidence never borrow progress from matching kanji cards."""

from types import SimpleNamespace

from katanki.anki.identities import MODEL_MARKER
from katanki.anki.primitive_statistics import read_primitive_progress


def test_parts_ownership_non_han_keys_and_conservative_states():
    class Note(dict):
        def cards(self):
            return self["cards"]

    def card(cid, kind, interval=30, queue=2):
        return SimpleNamespace(id=cid, type=kind, ivl=interval, queue=queue, reps=5, lapses=1)

    models = [
        {"id": mid, "name": marker, MODEL_MARKER: marker, "flds": [{"name": field}]}
        for mid, marker, field in (
            (1, "primitive-recognition", "Component"),
            (2, "primitive-production", "Component"),
            (3, "kanji-recognition", "Character"),
            (4, "primitive-recognition", "Wrong"),
        )
    ]
    notes = {
        10: Note(Component="kvg:graphical-part", cards=[card(1, 2, queue=-1), card(2, 3)]),
        11: Note(Component="日", cards=[]),
        12: Note(Component="日", cards=[card(3, 2)]),
        13: Note(Component=" ", cards=[]),
        20: Note(Component="kvg:graphical-part", cards=[card(4, 0)]),
    }
    col = SimpleNamespace(
        models=SimpleNamespace(all=lambda: models),
        find_notes=lambda search: {"mid:1": [10, 11, 12, 13], "mid:2": [20]}[search],
        get_note=notes.__getitem__,
    )
    result = read_primitive_progress(col)
    assert result.state("kvg:graphical-part", "recognition") == "relearning"
    assert result.state("kvg:graphical-part", "writing") == "new"
    assert result.state("日", "writing") == "missing"
    assert result.details("日")["recognition"]["note_ids"] == [11, 12]
    assert result.cards[0].suspended
    assert len(result.warnings) == 2
    assert len(result.payload(("日", "absent"))["rows"]) == 2


def test_targets_use_provider_keys_and_preserve_missing_notes(monkeypatch):
    from katanki.anki import primitive_statistics as module
    from katanki.stats.progress import ProgressSnapshot

    monkeypatch.setattr(module, "load_settings", lambda _: SimpleNamespace(dictionaries=()))
    monkeypatch.setattr(
        module,
        "read_primitive_progress",
        lambda _: ProgressSnapshot((), (("owned:no-cards", "recognition", 1),)),
    )
    registry = SimpleNamespace(lists=(SimpleNamespace(id="source"),), targets=lambda _: ("日",))
    monkeypatch.setattr(module, "load_target_registry", lambda **_: registry)
    monkeypatch.setattr(module, "dictionary_sources", lambda *_, **__: {"strokes": "local"})
    monkeypatch.setattr(
        module,
        "list_datasets",
        lambda: [SimpleNamespace(id="strokes", format="kanjivg_svg", bundled=None)],
    )

    class Provider:
        def __init__(self, path):
            assert path == "local"

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def lookup_strokes(self, character):
            assert character == "日"
            return SimpleNamespace(
                component_entries=(
                    SimpleNamespace(key="graphical:1", label="Shape"),
                    SimpleNamespace(key="graphical:1", label="Shape"),
                )
            )

    monkeypatch.setattr(module, "KanjiVgSvg", Provider)
    progress, labels, warnings = module.primitive_snapshot(object())
    assert labels == {"owned:no-cards": "owned:no-cards", "graphical:1": "Shape"}
    assert "日" not in labels
    assert progress.state("graphical:1", "recognition") == "missing"
    assert progress.details("owned:no-cards")["recognition"]["note_ids"] == [1]
    assert not warnings


def test_unavailable_targets_preserve_owned_parts_and_warn(monkeypatch):
    from katanki.anki import primitive_statistics as module
    from katanki.stats.progress import ProgressSnapshot

    owned = ProgressSnapshot((), (("owned", "recognition", 1),))
    monkeypatch.setattr(module, "load_settings", lambda _: SimpleNamespace(dictionaries=()))
    monkeypatch.setattr(module, "read_primitive_progress", lambda _: owned)

    def unavailable(**_):
        raise OSError("source missing")

    monkeypatch.setattr(module, "load_target_registry", unavailable)
    progress, labels, warnings = module.primitive_snapshot(object())
    assert progress is owned
    assert labels == {"owned": "owned"}
    assert warnings == ("Component targets unavailable: source missing",)


def test_unsupported_card_evidence_does_not_erase_note_presence():
    class Note(dict):
        def cards(self):
            return [SimpleNamespace(id=1, type=99, ivl=30)]

    model = {
        "id": 1,
        "name": "Parts",
        MODEL_MARKER: "primitive-recognition",
        "flds": [{"name": "Component"}],
    }
    collection = SimpleNamespace(
        models=SimpleNamespace(all=lambda: [model]),
        find_notes=lambda _: [2],
        get_note=lambda _: Note(Component="graphical:key"),
    )
    progress = read_primitive_progress(collection)
    assert progress.state("graphical:key", "recognition") == "missing"
    assert progress.details("graphical:key")["recognition"]["note_ids"] == [2]
    assert progress.warnings == ("Card 1: unsupported card type; excluded.",)
