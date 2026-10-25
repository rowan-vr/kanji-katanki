"""Read-only Parts evidence and graphical component targets from KanjiVG."""

from ..config import load_settings
from ..dictionaries.adapters.kanjivg_svg import KanjiVgSvg
from ..dictionaries.preferences import dictionary_sources
from ..dictionaries.registry import bundled_path, list_datasets, verify_bundle
from ..generation.planner import Identity
from ..stats.progress import CardEvidence, ProgressSnapshot, card_state
from ..stats.sources import load_target_registry
from .identities import MODEL_MARKER
from .target_lists import store_for_collection


def read_primitive_progress(collection):
    cards, notes, warnings, seen = [], [], [], set()
    modes = {"primitive-recognition": "recognition", "primitive-production": "writing"}
    for model in collection.models.all():
        marker = model.get(MODEL_MARKER)
        if marker not in modes:
            continue
        if "Component" not in {field["name"] for field in model["flds"]}:
            warnings.append(f"{model['name']}: missing Component field; excluded.")
            continue
        for note_id in sorted(set(collection.find_notes(f"mid:{model['id']}"))):
            note = collection.get_note(note_id)
            try:
                key = Identity(marker, note["Component"]).key
            except ValueError:
                warnings.append(f"Note {note_id}: invalid Component; excluded.")
                continue
            mode = modes[marker]
            notes.append((key, mode, note_id))
            for card in note.cards():
                if card.id in seen:
                    continue
                seen.add(card.id)
                try:
                    state = card_state(card.type, card.ivl)
                except ValueError:
                    warnings.append(f"Card {card.id}: unsupported card type; excluded.")
                    continue
                cards.append(
                    CardEvidence(
                        key,
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


def primitive_snapshot(collection):
    settings = load_settings(collection)
    progress = read_primitive_progress(collection)
    warnings = list(progress.warnings)
    labels = {key: key for key, _, _ in progress.notes}
    try:
        registry = load_target_registry(choices=settings.dictionaries)
        if getattr(collection, "path", None):
            for target in store_for_collection(collection).load():
                registry.register(target)
        characters = registry.targets(tuple((target.id, None) for target in registry.lists))
        paths = dictionary_sources(settings.dictionaries, capability="strokes")
        for manifest in list_datasets():
            if manifest.id not in paths or manifest.format != "kanjivg_svg":
                continue
            path = paths[manifest.id]
            if manifest.bundled and path.resolve() == bundled_path(manifest.bundled["path"]):
                verify_bundle(manifest)
            with KanjiVgSvg(path) as provider:
                for character in characters:
                    try:
                        entry = provider.lookup_strokes(character)
                        if entry:
                            for component in entry.component_entries:
                                key = Identity("primitive-recognition", component.key).key
                                labels[key] = component.label or key
                    except (ValueError, OSError) as error:
                        warnings.append(f"{character}: {error}")
        if not paths:
            warnings.append("No stroke source enabled; only owned Parts are shown.")
    except (ValueError, OSError) as error:
        warnings.append(f"Component targets unavailable: {error}")
    return progress, labels, tuple(warnings)
