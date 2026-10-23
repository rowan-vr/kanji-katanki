"""Independent card preferences, backwards migration, and invalid-data handling."""

import copy
import json
from unittest.mock import Mock

import pytest

from katanki.config import (
    GENERATION_CATEGORIES,
    CardSettings,
    Settings,
    from_dict,
    load_settings,
)


def test_independent_card_preferences_survive_json_roundtrip():
    settings = Settings(
        cards=(
            CardSettings(False, "discovered", False, False, False),
            CardSettings(True, "discovered_and_default", True, True, False),
            CardSettings(show_name=False),
        )
    )
    restored = from_dict(json.loads(json.dumps(settings.to_dict())))
    assert restored == settings
    for index, category in enumerate(GENERATION_CATEGORIES):
        assert restored.card_settings(category) == settings.cards[index]


@pytest.mark.parametrize("version", [1, 2, 3, 4])
def test_older_settings_migrate_with_card_defaults_without_modifying_input(version):
    saved = Settings(destination_deck_id=40, include_primitives=True).to_dict()
    saved["version"] = version
    saved.pop("cards")
    original = copy.deepcopy(saved)
    restored = from_dict(saved)
    assert saved == original
    assert restored.destination_deck_id == 40
    assert restored.include_primitives is True
    assert restored.to_dict()["version"] == 5
    for category in GENERATION_CATEGORIES:
        assert restored.card_settings(category) == CardSettings()
        assert restored.card_settings(category).auto_refresh is True


def test_missing_category_and_fields_receive_defaults():
    restored = from_dict({"version": 5, "cards": {"production": {"furigana": True}}})
    assert restored.card_settings("production") == CardSettings(furigana=True)
    assert restored.card_settings("recognition") == CardSettings()
    assert restored.card_settings("parts") == CardSettings()


@pytest.mark.parametrize(
    "cards",
    [
        [],
        {"recognition": None},
        {"production": []},
        {"parts": {"example_source": "default"}},
        {"parts": {"example_source": []}},
        *(
            {"recognition": {field: value}}
            for field in ("show_examples", "furigana", "auto_refresh", "include_new", "show_name")
            for value in ("false", 0, None)
        ),
    ],
)
def test_invalid_card_settings_fail_without_writes(cards):
    collection = Mock()
    collection.get_config.return_value = {"version": 5, "cards": cards}
    with pytest.raises(ValueError):
        load_settings(collection)
    collection.set_config.assert_not_called()


def test_incomplete_card_categories_are_rejected():
    with pytest.raises(ValueError):
        Settings(cards=(CardSettings(),))


def test_existing_version_five_settings_default_to_showing_part_name():
    saved = Settings().to_dict()
    for profile in saved["cards"].values():
        profile.pop("show_name")
    assert from_dict(saved).card_settings("parts").show_name is True
