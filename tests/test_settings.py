"""Settings round-trips and invalid data must never overwrite saved configuration."""

import json
from unittest.mock import Mock

import pytest

from katanki.config import CONFIG_KEY, Settings, SourceRule, from_dict, load_settings, save_settings


def test_defaults_are_safe_and_collection_independent():
    assert from_dict(None) == Settings()
    assert Settings().sources == ()
    assert Settings().include_primitives is False
    assert Settings().generation_settings("production").auto_generate is True
    saved = Settings().to_dict()
    saved["generation"]["production"]["auto_generate"] = False
    assert from_dict(saved).generation_settings("production").auto_generate is False


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
    assert stored[CONFIG_KEY]["version"] == 8


@pytest.mark.parametrize(
    "data",
    [
        [],
        {},
        {"version": True},
        {"version": 0},
        {"version": 9},
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
    assert settings.to_dict()["version"] == 8
    assert json.dumps(data) == original


def test_category_settings_roundtrip_and_version_two_migration():
    from katanki.config import GenerationSettings

    settings = Settings(
        generation=(
            GenerationSettings(True, 10, ("katanki",), True, ("source::NIJ::*",)),
            GenerationSettings(True, 20, ("production",), True),
            GenerationSettings(False, 30, ("parts",)),
        )
    )
    assert from_dict(json.loads(json.dumps(settings.to_dict()))) == settings
    legacy = from_dict({"version": 2, "destination_deck_id": 40, "include_primitives": True})
    assert legacy.generation_settings("recognition") == GenerationSettings(True, 40)
    assert legacy.generation_settings("production") == GenerationSettings(True, 40)
    assert legacy.generation_settings("parts") == GenerationSettings(True, 40)


@pytest.mark.parametrize(
    "entry",
    [
        [],
        {"auto_generate": "false"},
        {"target_deck_id": True},
        {"default_tags": "tag"},
        {"default_tags": ["two words"]},
        {"copy_source_tags": 1},
        {"source_tag_patterns": [""]},
    ],
)
def test_invalid_generation_profiles_are_rejected(entry):
    with pytest.raises(ValueError):
        from_dict({"version": 3, "generation": {"recognition": entry}})


def test_statistics_selection_roundtrip_and_legacy_default():
    settings = Settings(statistics_selection=(("user:course", "chapter-1"), ("joyo", None)))
    assert from_dict(json.loads(json.dumps(settings.to_dict()))) == settings
    assert from_dict({"version": 7}).statistics_selection == ()
    for invalid in ["joyo", ["joyo"], [["joyo", 42]], [["joyo", None, "extra"]]]:
        with pytest.raises(ValueError, match="statistics"):
            from_dict({"version": 8, "statistics_selection": invalid})


def test_optional_reading_field_round_trip_and_legacy_default():
    settings = Settings((SourceRule("*", 30, ("Expression",), reading_field="Reading"),))
    assert from_dict(settings.to_dict()) == settings
    saved = settings.to_dict()
    del saved["sources"][0]["reading_field"]
    assert from_dict(saved).sources[0].reading_field is None
