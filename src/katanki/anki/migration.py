"""Reviewed card conversion using Anki APIs; original card IDs and revlog survive."""

import json
import unicodedata
from collections import Counter
from dataclasses import dataclass, replace

from ..common.characters import is_kanji
from ..common.models import ScanResult
from ..config import load_settings
from ..dictionaries.manager import DictionaryManager
from ..dictionaries.preferences import dictionary_sources
from ..dictionaries.words import selected_words
from ..generation.cards import CSS, CardContent, note_type_spec
from ..generation.discovery import visible_text
from ..generation.planner import GenerationPlan, Identity, LearningUnit, PlanItem
from ..generation.preview import GenerationPreview, build_preview
from .analysis import analyze_scan
from .generation import _validate_prompts
from .identities import MODEL_MARKER, owned_identities

CATEGORIES = {
    "recognition": "kanji-recognition",
    "production": "kanji-production",
}


@dataclass(frozen=True)
class MigrationSource:
    category: str
    deck_id: int
    model_id: int
    field: str


@dataclass(frozen=True)
class MigrationItem:
    card_id: int
    note_id: int
    identity: Identity
    content: CardContent
    card_snapshot: bytes
    note_snapshot: str
    history_snapshot: tuple


@dataclass(frozen=True)
class MigrationPlan:
    sources: tuple[MigrationSource, ...]
    items: tuple[MigrationItem, ...]
    warnings: tuple[str, ...]
    settings: object
    models_snapshot: str


def _prompt_preview(items):
    return GenerationPreview(
        GenerationPlan(tuple(PlanItem(LearningUnit(i.identity), "create", "") for i in items)),
        tuple(i.content for i in items),
        (),
    )


def _schedule(card):
    data = card._to_backend_card()
    for field in ("note_id", "template_idx", "mtime_secs", "usn"):
        data.ClearField(field)
    return data.SerializeToString()


def _models_snapshot(collection):
    return json.dumps(collection.models.all(), sort_keys=True)


def _note_snapshot(note):
    return json.dumps(
        {
            "id": note.id,
            "guid": note.guid,
            "model": note.mid,
            "fields": dict(note.items()),
            "tags": note.tags,
        },
        sort_keys=True,
    )


def _history(collection, card_id):
    return tuple(
        tuple(row)
        for row in collection.db.all("select * from revlog where cid = ? order by id", card_id)
    )


def _is_radical(character):
    return unicodedata.name(character, "").startswith(("CJK RADICAL ", "KANGXI RADICAL "))


def _notify(progress, message, current=0, total=0):
    if progress:
        progress(message, current, total)


def _scan(collection, sources, *, progress=None):
    if not sources:
        raise ValueError("Choose a source deck for recognition or production.")
    cards, warnings = [], []
    seen = set()
    for source in sources:
        if source.category not in CATEGORIES:
            raise ValueError("Unknown migration category.")
        model = collection.models.get(source.model_id)
        if model is None or model.get(MODEL_MARKER):
            raise ValueError("Select an existing source note type that is not owned by Katanki.")
        if model.get("type") != 0:
            raise ValueError("Cloze note types cannot be migrated.")
        if source.field not in {f["name"] for f in model["flds"]}:
            raise ValueError("The selected kanji field no longer exists.")
        if collection.decks.get(source.deck_id, default=False) is None:
            raise ValueError("The selected source deck no longer exists.")
        # Exact deck membership, with filtered cards located by their home deck.
        _notify(progress, f"Finding {source.category} source cards…")
        card_ids = sorted(collection.find_cards(f"mid:{source.model_id}"))
        for index, cid in enumerate(card_ids, 1):
            _notify(progress, f"Scanning {source.category} source cards", index, len(card_ids))
            card = collection.get_card(cid)
            if (card.odid or card.did) != source.deck_id:
                continue
            if cid in seen:
                raise ValueError("The same source card is selected for multiple categories.")
            seen.add(cid)
            note = collection.get_note(card.nid)
            key = visible_text(note[source.field]).strip()
            if len(key) != 1 or not (is_kanji(key) or _is_radical(key)):
                warnings.append(
                    f"Card {cid}: field must contain exactly one kanji or radical character; "
                    "skipped."
                )
                continue
            if card.odid:
                warnings.append(f"Card {cid}: return it from its filtered deck first; skipped.")
                continue
            identity = Identity(CATEGORIES[source.category], key)
            cards.append((card, note, identity))
    return cards, warnings


def prepare_migration(collection, sources, *, settings=None, progress=None):
    sources = tuple(sources)
    settings = settings or load_settings(collection)
    candidates, warnings = _scan(collection, sources, progress=progress)
    if not candidates:
        return MigrationPlan(sources, (), tuple(warnings), settings, _models_snapshot(collection))
    keys = tuple(dict.fromkeys(identity.key for _, _, identity in candidates))
    _notify(progress, f"Loading dictionaries and stroke data for {len(keys):,} characters…")
    report = analyze_scan(
        collection, ScanResult(0, keys), dictionary_sources(settings.dictionaries)
    )
    warnings.extend(report.warnings)
    kanji = {entry.character for entry in report.entries}
    components = {part.key: part for stroke in report.strokes for part in stroke.component_entries}
    strokes = {stroke.character: stroke for stroke in report.strokes}
    # Missing dictionary entries alone are not evidence that a character is a part.
    # Look up graphical data independently, since normal discovery only loads kanji strokes.
    unmatched = set(keys) - kanji
    if unmatched:
        with DictionaryManager(dictionary_sources(settings.dictionaries)) as manager:
            _notify(progress, "Checking part stroke data…")
            for index, key in enumerate(sorted(unmatched), 1):
                _notify(progress, "Checking part stroke data", index, len(unmatched))
                try:
                    stroke = manager.lookup_strokes(key)
                except (ValueError, OSError) as error:
                    warnings.append(f"{key}: part stroke data unavailable ({error}).")
                    continue
                if stroke:
                    strokes[key] = stroke
                    components.update((part.key, part) for part in stroke.component_entries)
            report = replace(
                report,
                attribution=tuple(
                    dict.fromkeys((*report.attribution, *manager.card_attribution()))
                ),
            )
    _notify(progress, "Identifying kanji and parts, and checking existing cards…")
    classified = []
    for card, note, identity in candidates:
        key = identity.key
        is_part = _is_radical(key) or (key not in kanji and key in components)
        if is_part:
            mode = identity.note_type.rsplit("-", 1)[1]
            identity = Identity(f"primitive-{mode}", key)
        classified.append((card, note, identity))
    counts = Counter(identity for _, _, identity in classified)
    existing = {}
    for kind in {identity.note_type for _, _, identity in classified}:
        existing.update(owned_identities(collection, note_type=kind))
    eligible = []
    for card, note, identity in classified:
        if counts[identity] > 1 or identity in existing:
            warnings.append(
                f"Card {card.id}: duplicate {identity.key} / {identity.note_type}; skipped."
            )
        else:
            eligible.append((card, note, identity))
    if not eligible:
        return MigrationPlan(sources, (), tuple(warnings), settings, _models_snapshot(collection))
    _notify(progress, "Loading vocabulary examples…")
    words = selected_words(
        settings.dictionaries,
        progress=((lambda message: _notify(progress, message)) if progress else None),
    )
    _notify(progress, f"Preparing content for {len(eligible):,} cards…")
    preview = build_preview(
        report,
        (),
        recognition=tuple(i.key for _, _, i in eligible if i.note_type == "kanji-recognition"),
        production=tuple(i.key for _, _, i in eligible if i.note_type == "kanji-production"),
        include_primitives=False,
        card_settings={c: settings.card_settings(c) for c in (*CATEGORIES, "parts")},
        word_suggestions=words,
        progress=(lambda message: _notify(progress, message)) if progress else None,
    )
    _validate_prompts(collection, preview)
    available = {item.unit.identity for item in preview.plan.items if item.outcome == "create"}
    contents = {
        content.identity: content for content in preview.contents if content.identity in available
    }
    for card, note, identity in eligible:
        if identity.kind != "primitive":
            continue
        part = components.get(identity.key)
        stroke = strokes.get(identity.key)
        if part is None and stroke is None:
            continue
        # Source meaning/name fields provide a real production clue for a part.
        names = (
            "Name",
            "name",
            "Meaning",
            "meaning",
            "Meanings",
            "meanings",
            "Keyword",
            "keyword",
            "Mnemonic",
            "mnemonic",
        )
        name = next(
            (
                visible_text(note[field]).strip()
                for field in names
                if field in note.keys() and visible_text(note[field]).strip()
            ),
            "",
        )
        if identity.note_type == "primitive-production" and (not name or name == identity.key):
            warnings.append(
                f"Card {card.id}: "
                "part writing requires a source Name, Meaning or Keyword field; skipped."
            )
            continue
        options = settings.card_settings("parts")
        contents[identity] = CardContent(
            identity,
            part.label if part else identity.key,
            svg=part.svg if part else stroke.svg,
            components=part.prerequisites if part else stroke.components,
            prompt=name if identity.note_type == "primitive-production" else "",
            meanings=(name,) if name else (),
            attribution=report.attribution,
            show_examples=options.show_examples,
        )
    items = []
    _notify(progress, "Reading scheduling and review history…")
    for index, (card, note, identity) in enumerate(eligible, 1):
        _notify(progress, f"Reading history for {identity.key}", index, len(eligible))
        if identity not in contents:
            warnings.append(
                f"Card {card.id}: usable dictionary content/clues unavailable; skipped."
            )
            continue
        items.append(
            MigrationItem(
                card.id,
                note.id,
                identity,
                contents[identity],
                card._to_backend_card().SerializeToString(),
                _note_snapshot(note),
                _history(collection, card.id),
            )
        )
    _notify(progress, "Checking production clues and finishing preview…")
    _validate_prompts(collection, _prompt_preview(items))
    return MigrationPlan(
        sources, tuple(items), tuple(warnings), settings, _models_snapshot(collection)
    )


def apply_migration(collection, plan, *, progress=None):
    """Keep card IDs and every scheduling attribute; never rewrite review logs."""
    from anki.collection import OpChanges

    if not plan.items:
        return OpChanges()
    if (
        load_settings(collection) != plan.settings
        or _models_snapshot(collection) != plan.models_snapshot
    ):
        raise ValueError("Settings or note types changed; preview migration again.")
    selected, _ = _scan(collection, plan.sources, progress=progress)
    selected_ids = {card.id for card, _, _ in selected}
    counts = Counter((i.note_type.rsplit("-", 1)[1], i.key) for _, _, i in selected)
    _validate_prompts(collection, _prompt_preview(plan.items))
    existing = {}
    for kind in {item.identity.note_type for item in plan.items}:
        existing.update(owned_identities(collection, note_type=kind))
    schedules = {}
    _notify(progress, "Rechecking approved cards before conversion…")
    for index, item in enumerate(plan.items, 1):
        _notify(progress, f"Validating {item.identity.key}", index, len(plan.items))
        card = collection.get_card(item.card_id)
        if (
            counts[(item.identity.note_type.rsplit("-", 1)[1], item.identity.key)] != 1
            or item.card_id not in selected_ids
            or card._to_backend_card().SerializeToString() != item.card_snapshot
            or _note_snapshot(collection.get_note(item.note_id)) != item.note_snapshot
            or _history(collection, item.card_id) != item.history_snapshot
            or item.identity in existing
        ):
            raise ValueError("Source cards or Katanki ownership changed; preview migration again.")
        schedules[item.card_id] = _schedule(card)
    models = {}
    for kind in {item.identity.note_type for item in plan.items}:
        matches = [m for m in collection.models.all() if m.get(MODEL_MARKER) == kind]
        if len(matches) > 1:
            raise ValueError("Multiple Katanki note types match; resolve them before migration.")
        if matches:
            model = matches[0]
            if len(model["tmpls"]) != 1 or model["tmpls"][0]["ord"] != 0:
                raise ValueError("Katanki note types must have one card template.")
            if not set(note_type_spec(kind).fields) <= {f["name"] for f in model["flds"]}:
                raise ValueError("Katanki note type fields are incomplete; refresh it first.")
            models[kind] = model
    # Validate serialization before the first write.
    fields = {item.card_id: item.content.fields() for item in plan.items}
    undo = collection.add_custom_undo_entry("Katanki: migrate cards")
    mutated = False

    def merge():
        nonlocal mutated
        mutated = True
        return collection.merge_undo_entries(undo)

    try:
        _notify(progress, "Preparing Katanki note types…")
        for kind in {item.identity.note_type for item in plan.items}:
            spec = note_type_spec(kind)
            model = models.get(kind)
            if model is None:
                model = collection.models.new(spec.name)
                model[MODEL_MARKER], model["css"] = kind, CSS
                for name in spec.fields:
                    collection.models.add_field(model, collection.models.new_field(name))
                template = collection.models.new_template(kind)
                template["qfmt"], template["afmt"] = spec.front, spec.back
                collection.models.add_template(model, template)
                added = collection.models.add_dict(model)
                merge()
                model = collection.models.get(added.id)
            else:
                legacy = next((f for f in model["flds"] if f["name"] == "MigrationSource"), None)
                if legacy is not None:
                    collection.models.remove_field(model, legacy)
                    collection.models.update_dict(model)
                    merge()
            models[kind] = model
        _notify(progress, "Converting cards…")
        for index, item in enumerate(plan.items, 1):
            _notify(progress, f"Converting {item.identity.key}", index, len(plan.items))
            card = collection.get_card(item.card_id)
            old = collection.get_note(item.note_id)
            note = collection.new_note(models[item.identity.note_type])
            for name, value in fields[item.card_id].items():
                note[name] = value
            note.tags = list(old.tags)
            collection.add_note(note, card.did)
            merge()
            placeholder = note.cards()[0]
            # Transfer the original card, not its scheduling values, to the new note.
            card.nid, card.ord = note.id, 0
            collection.update_card(card)
            merge()
            collection.remove_cards_and_orphaned_notes([placeholder.id])
            merge()
        _notify(progress, "Removing empty source notes…")
        for nid in {item.note_id for item in plan.items}:
            if not collection.get_note(nid).cards():
                collection.remove_notes([nid])
                merge()
        _notify(progress, "Verifying scheduling and review history…")
        for index, item in enumerate(plan.items, 1):
            _notify(progress, "Verifying preserved scheduling and history", index, len(plan.items))
            if _schedule(collection.get_card(item.card_id)) != schedules[item.card_id]:
                raise RuntimeError("Scheduling verification failed.")
            if _history(collection, item.card_id) != item.history_snapshot:
                raise RuntimeError("Review history verification failed.")
        _notify(progress, "Finishing conversion…")
        return collection.merge_undo_entries(undo)
    except Exception:
        if mutated:
            _notify(progress, "Reverting incomplete conversion…")
            collection.merge_undo_entries(undo)
            collection.undo()
        raise
