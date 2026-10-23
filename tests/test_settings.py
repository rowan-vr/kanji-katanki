"""Settings round-trips and invalid data must never overwrite saved configuration."""

import json
from unittest.mock import Mock

import pytest

from katanki.config import CONFIG_KEY, Settings, SourceRule, from_dict, load_settings, save_settings


def test_defaults_are_safe_and_collection_independent():
    assert from_dict(None) == Settings()
    assert Settings().sources == ()
    assert Settings().include_primitives is False


def test_saved_settings_survive_json_storage_and_reloading():
    stored = {}
    collection = Mock()
    collection.get_config.side_effect = lambda key, default: stored.get(key, default)
    collection.set_config.side_effect = lambda key, value: stored.update(
        {key: json.loads(json.dumps(value))}
    )
    settings = Settings(
        (
            SourceRule("*", 30, ("Expression", "Word")),
            SourceRule("Japanese::Vocab", 31, ("Front",)),
        ),
        40,
        True,
    )
    save_settings(collection, settings)
    assert load_settings(collection) == settings
    assert set(stored) == {CONFIG_KEY}
    assert stored[CONFIG_KEY]["version"] == 2


@pytest.mark.parametrize(
    "data",
    [
        [],
        {},
        {"version": True},
        {"version": 0},
        {"version": 3},
        {"version": 2, "sources": {}},
        {"version": 2, "sources": [{"deck_pattern": "*", "note_type_id": 1, "fields": []}]},
        {"version": 1, "source": []},
        {"version": 1, "source": {"deck_ids": "10", "fields": ["Word"]}},
        {"version": 1, "source": {"deck_ids": [10], "fields": ["Word"]}},
        {"version": 1, "source": {"deck_ids": [], "fields": [], "note_type_id": 1}},
        {"version": 1, "destination_deck_id": True},
        {"version": 1, "destination_deck_id": -1},
        {"version": 1, "include_primitives": "false"},
    ],
)
def test_invalid_or_future_settings_are_rejected_without_writes(data):
    collection = Mock()
    collection.get_config.return_value = data
    with pytest.raises(ValueError):
        load_settings(collection)
    collection.set_config.assert_not_called()


def test_invalid_settings_cannot_be_saved():
    collection = Mock()
    with pytest.raises(ValueError):
        save_settings(collection, Settings(destination_deck_id=-1))
    collection.set_config.assert_not_called()


def test_version_one_migration_preserves_ids_preferences_and_original_data():
    data = {
        "version": 1,
        "source": {"deck_ids": [10, 20], "note_type_id": 30, "fields": ["Expression"]},
        "destination_deck_id": 40,
        "include_primitives": True,
    }
    original = json.dumps(data)
    settings = from_dict(data)
    assert settings == Settings((SourceRule("", 30, ("Expression",), (10, 20)),), 40, True)
    assert settings.to_dict()["version"] == 2
    assert json.dumps(data) == original
