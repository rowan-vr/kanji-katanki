"""Find generated notes by registered note type and ordinary content fields.

Deck membership never affects deduplication. Model metadata establishes ownership;
notes have no synthetic identity field or configuration scope.
"""

from ..generation.planner import NOTE_TYPES, Identity

MODEL_MARKER = "katanki_note_type"


def owned_identities(collection, *, note_type: str) -> dict[Identity, tuple[int, ...]]:
    if note_type not in NOTE_TYPES:
        raise ValueError("Unknown Katanki note type.")
    field = "Character" if note_type.startswith("kanji-") else "Component"
    found: dict[Identity, list[int]] = {}
    for model in collection.models.all():
        if model.get(MODEL_MARKER) != note_type:
            continue
        if field not in {item["name"] for item in model["flds"]}:
            raise ValueError(f"A Katanki note type is missing its {field} field.")
        model_id = model["id"]
        if type(model_id) is not int or model_id <= 0:
            raise ValueError("Invalid Katanki note type ID.")
        for note_id in sorted(set(collection.find_notes(f"mid:{model_id}"))):
            note = collection.get_note(note_id)
            try:
                identity = Identity(note_type, note[field])
            except ValueError as error:
                raise ValueError(f"Invalid Katanki {field} on note {note_id}.") from error
            found.setdefault(identity, []).append(note_id)
    return {identity: tuple(sorted(ids)) for identity, ids in found.items()}
