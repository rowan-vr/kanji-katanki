"""Read collection data only via Anki APIs; never retain live notes in the core."""

from collections.abc import Iterator

from ..common.models import NoteText, ScanSelection


def scan_sources(collection):
    decks = [(deck.id, deck.name) for deck in collection.decks.all_names_and_ids()]
    note_types = [
        (model["id"], model["name"], tuple(field["name"] for field in model["flds"]))
        for model in collection.models.all()
    ]
    return decks, sorted(note_types, key=lambda model: model[1])


def selected_notes(collection, selection: ScanSelection) -> Iterator[NoteText]:
    model = collection.models.get(selection.note_type_id)
    if model is None:
        raise ValueError("The selected note type no longer exists. Reopen Analyze Collection.")
    known_fields = {field["name"] for field in model["flds"]}
    if not set(selection.fields) <= known_fields:
        raise ValueError("The selected fields no longer exist. Reopen Analyze Collection.")
    deck_ids = {deck.id for deck in collection.decks.all_names_and_ids()}
    if not set(selection.deck_ids) <= deck_ids:
        raise ValueError("A selected deck no longer exists. Reopen Analyze Collection.")
    # Numeric IDs are validated by ScanSelection; names never become search syntax.
    decks = " or ".join(f"did:{deck_id}" for deck_id in selection.deck_ids)
    query = f"({decks}) mid:{selection.note_type_id}"
    for note_id in sorted(set(collection.find_notes(query))):
        note = collection.get_note(note_id)
        yield NoteText(tuple(note[field] for field in selection.fields))
