"""Read collection data only via Anki APIs; never retain live notes in the core."""

import re
from collections.abc import Iterator

from ..common.models import WORD_STATUS_ORDER, NoteText, ScanSelection
from ..config import SourceRule


def scan_sources(collection):
    decks = [(deck.id, deck.name) for deck in collection.decks.all_names_and_ids()]
    note_types = [
        (model["id"], model["name"], tuple(field["name"] for field in model["flds"]))
        for model in collection.models.all()
    ]
    return decks, sorted(note_types, key=lambda model: model[1])


def resolve_sources(collection, rules: tuple[SourceRule, ...]) -> tuple[ScanSelection, ...]:
    """Resolve literal deck choices or * patterns against the current deck catalog."""
    decks = dict(scan_sources(collection)[0])
    selections = []
    for rule in rules:
        if rule.deck_ids:
            if not set(rule.deck_ids) <= decks.keys():
                raise ValueError("A saved source deck is missing. Review Discovery settings.")
            names = [decks[deck_id] for deck_id in rule.deck_ids]
            ids = tuple(
                sorted(
                    deck_id
                    for deck_id, name in decks.items()
                    if any(name == parent or name.startswith(parent + "::") for parent in names)
                )
            )
        else:
            # Only * is special; punctuation and other Anki search syntax stay literal.
            pattern = re.compile(re.escape(rule.deck_pattern.strip()).replace(r"\*", ".*"))
            names = [name for name in decks.values() if pattern.fullmatch(name)]
            ids = tuple(
                sorted(
                    deck_id
                    for deck_id, name in decks.items()
                    if any(name == parent or name.startswith(parent + "::") for parent in names)
                )
            )
        if not ids:
            raise ValueError(f"No decks match {rule.deck_pattern!r}. Review Discovery settings.")
        selections.append(ScanSelection(ids, rule.note_type_id, rule.fields))
    if not selections:
        raise ValueError("Add at least one vocabulary source in Discovery settings.")
    return tuple(selections)


def selected_notes(
    collection,
    selection: ScanSelection | tuple[ScanSelection, ...],
    *,
    exact_deck_id: int | None = None,
) -> Iterator[NoteText]:
    selections = (selection,) if isinstance(selection, ScanSelection) else selection
    if not selections:
        raise ValueError("Select at least one vocabulary source.")
    # Validate every rule before searching; merge fields by note ID across overlaps.
    for source in selections:
        model = collection.models.get(source.note_type_id)
        if model is None:
            raise ValueError("The selected note type no longer exists. Review Discovery settings.")
        known_fields = {field["name"] for field in model["flds"]}
        if not set(source.fields) <= known_fields:
            raise ValueError("The selected fields no longer exist. Review Discovery settings.")
    deck_ids = {deck.id for deck in collection.decks.all_names_and_ids()}
    for source in selections:
        if not set(source.deck_ids) <= deck_ids:
            raise ValueError("A selected deck no longer exists. Review Discovery settings.")
    fields_by_note = {}
    for source in selections:
        decks = " or ".join(f"did:{deck_id}" for deck_id in source.deck_ids)
        query = f"({decks}) mid:{source.note_type_id}"
        for note_id in sorted(set(collection.find_notes(query))):
            if exact_deck_id is not None:
                note = collection.get_note(note_id)
                if not any(
                    (getattr(card, "odid", 0) or card.did) == exact_deck_id for card in note.cards()
                ):
                    continue
            fields_by_note.setdefault(note_id, {}).update(dict.fromkeys(source.fields))
    for note_id, fields in sorted(fields_by_note.items()):
        note = collection.get_note(note_id)
        # Card type remains meaningful for suspended/buried cards too; queue is
        # temporary. Review = graduated, relearning = currently learning again.
        cards = note.cards() if hasattr(note, "cards") else ()
        statuses = [
            {0: "new", 1: "learning", 2: "learned", 3: "relearning"}.get(card.type, "exists")
            for card in cards
        ]
        status = min(statuses, key=WORD_STATUS_ORDER.__getitem__, default="missing")
        yield NoteText(
            tuple(note[field] for field in fields), tuple(getattr(note, "tags", ())), status
        )
