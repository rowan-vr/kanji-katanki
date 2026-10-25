"""Read-only snapshots of owned kanji cards, independent of vocabulary exposure."""

from ..common.characters import is_kanji
from ..config import load_settings
from ..dictionaries.adapters.kanjidic2_xml import KanjidicXml
from ..dictionaries.adapters.kanjivg_svg import KanjiVgSvg
from ..dictionaries.preferences import dictionary_sources
from ..dictionaries.registry import bundled_path, list_datasets, verify_bundle
from ..stats.progress import CardEvidence, ProgressSnapshot, card_state
from ..stats.sources import load_target_registry
from .identities import MODEL_MARKER


def read_progress(collection) -> ProgressSnapshot:
    cards, notes, warnings = [], [], []
    modes = {"kanji-recognition": "recognition", "kanji-production": "writing"}
    seen = set()
    for model in collection.models.all():
        mode = modes.get(model.get(MODEL_MARKER))
        if mode is None:
            continue
        if "Character" not in {field["name"] for field in model["flds"]}:
            warnings.append(f"{model['name']}: missing Character field; excluded from statistics.")
            continue
        for note_id in sorted(set(collection.find_notes(f"mid:{model['id']}"))):
            note = collection.get_note(note_id)
            character = note["Character"]
            if not is_kanji(character):
                warnings.append(f"Note {note_id}: invalid Character; excluded from statistics.")
                continue
            notes.append((character, mode, note_id))
            for card in note.cards():
                if card.id in seen:
                    continue
                seen.add(card.id)
                try:
                    state = card_state(card.type, card.ivl)
                except ValueError:
                    warnings.append(
                        f"Card {card.id}: unsupported card type; excluded from statistics."
                    )
                    continue
                cards.append(
                    CardEvidence(
                        character,
                        mode,
                        card.id,
                        note_id,
                        state,
                        card.ivl,
                        card.reps,
                        card.lapses,
                        card.queue == -1,
                        card.queue in (-2, -3),
                    )
                )
    return ProgressSnapshot(tuple(cards), tuple(notes), tuple(warnings))


def dashboard_snapshot(collection):
    settings = load_settings(collection)
    registry = load_target_registry(choices=settings.dictionaries)
    progress = read_progress(collection)
    targets = tuple(
        dict.fromkeys(
            [
                *registry.targets(tuple((target.id, None) for target in registry.lists)),
                *(card.character for card in progress.cards),
            ]
        )
    )
    metadata, warnings = {}, []
    try:
        paths = dictionary_sources(settings.dictionaries, capability="kanji")
        for manifest in list_datasets():
            if manifest.id not in paths:
                continue
            path = paths[manifest.id]
            if manifest.bundled and path.resolve() == bundled_path(manifest.bundled["path"]):
                verify_bundle(manifest)
            provider = KanjidicXml(path)
            for character in targets:
                entry = provider.lookup_kanji(character)
                if entry:
                    metadata[character] = {
                        "meanings": entry.meanings,
                        "on": entry.on_readings,
                        "kun": entry.kun_readings,
                    }
    except (ValueError, OSError) as error:
        warnings.append(f"Dictionary search data unavailable: {error}")
    return registry, progress, metadata, warnings


def character_details(collection, progress: ProgressSnapshot, character: str) -> dict:
    settings = load_settings(collection)
    result = {"character": character, "evidence": progress.details(character), "warnings": []}
    # Load only the required dictionary capabilities; word dictionaries are irrelevant.
    for capability, format_name in (("kanji", "kanjidic2_xml"), ("strokes", "kanjivg_svg")):
        try:
            paths = dictionary_sources(settings.dictionaries, capability=capability)
            for manifest in list_datasets():
                if manifest.id not in paths or manifest.format != format_name:
                    continue
                path = paths[manifest.id]
                if manifest.bundled and path.resolve() == bundled_path(manifest.bundled["path"]):
                    verify_bundle(manifest)
                if capability == "kanji":
                    entry = KanjidicXml(path).lookup_kanji(character)
                    if entry:
                        result["dictionary"] = {
                            "meanings": entry.meanings,
                            "on": entry.on_readings,
                            "kun": entry.kun_readings,
                            "strokes": entry.stroke_count,
                        }
                else:
                    with KanjiVgSvg(path) as provider:
                        entry = provider.lookup_strokes(character)
                        if entry:
                            result["svg"] = entry.svg.decode("utf-8")
        except (ValueError, OSError) as error:
            result["warnings"].append(f"{capability}: {error}")
    for mode in result["evidence"].values():
        answered, passed = 0, 0
        for card in mode["cards"]:
            logs = collection.get_review_logs(card["card_id"])
            # Exclude manual reschedules/reset entries (rating zero).
            ratings = [log.button_chosen for log in logs if 1 <= log.button_chosen <= 4]
            answered += len(ratings)
            passed += sum(rating > 1 for rating in ratings)
        mode["answered"] = answered
        mode["passed"] = passed
    return result
