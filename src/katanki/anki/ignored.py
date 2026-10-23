"""Collection-local ignored card identities; no note/card mutations."""

from ..generation.planner import Identity

IGNORED_KEY = "katanki_ignored_cards"


def load_ignored(collection) -> frozenset[Identity]:
    data = collection.get_config(IGNORED_KEY, [])
    if not isinstance(data, list):
        raise ValueError("Invalid ignored-card settings. Saved data was preserved.")
    identities = []
    for entry in data:
        if not isinstance(entry, dict) or set(entry) != {"note_type", "key"}:
            raise ValueError("Invalid ignored-card identity. Saved data was preserved.")
        identities.append(Identity(entry["note_type"], entry["key"]))
    return frozenset(identities)


def save_ignored(collection, identities):
    identities = sorted(set(identities))
    if any(not isinstance(identity, Identity) for identity in identities):
        raise ValueError("Invalid ignored-card identity.")
    collection.set_config(
        IGNORED_KEY,
        [{"note_type": identity.note_type, "key": identity.key} for identity in identities],
    )
