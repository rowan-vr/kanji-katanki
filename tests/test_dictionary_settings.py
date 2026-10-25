"""Saved dataset choices, format checks, and backwards-compatible defaults."""

from pathlib import Path

import pytest

from katanki.config import DictionaryChoice, Settings, from_dict
from katanki.dictionaries.preferences import check_dictionary, dictionary_sources
from katanki.dictionaries.registry import bundled_sources

FIXTURES = Path(__file__).parent / "fixtures"


def test_defaults_use_bundled_datasets_and_disabled_choices_remove_them():
    assert dictionary_sources(()) == {
        key: path
        for key, path in bundled_sources().items()
        if key not in {"school-grades", "joyo", "jlpt-openjlpt"}
    }
    assert dictionary_sources((DictionaryChoice("kanjidic2", "disabled"),)) == {
        "kanjivg": bundled_sources()["kanjivg"],
        "jitendex": bundled_sources()["jitendex"],
    }
    assert (
        dictionary_sources(tuple(DictionaryChoice(key, "disabled") for key in bundled_sources()))
        == {}
    )


def test_local_choices_are_used_instead_of_bundles_and_persist():
    choices = (
        DictionaryChoice("kanjidic2", "local", str(FIXTURES / "kanjidic2.xml")),
        DictionaryChoice("kanjivg", "disabled"),
    )
    settings = Settings(dictionaries=choices)
    assert from_dict(settings.to_dict()) == settings
    assert dictionary_sources(choices) == {
        "kanjidic2": FIXTURES / "kanjidic2.xml",
        "jitendex": bundled_sources()["jitendex"],
    }
    assert "SHA-256" in check_dictionary(choices[0])
    assert "Disabled" in check_dictionary(choices[1])


def test_local_stroke_checks_validate_an_actual_sample_and_reject_empty_or_broken_files(tmp_path):
    result = check_dictionary(DictionaryChoice("kanjivg", "local", str(FIXTURES / "kanjivg")))
    assert "Sample stroke 景 validated" in result
    assert "KanjiVG" in result and "SHA-256" in result
    with pytest.raises(ValueError, match="No canonical stroke"):
        check_dictionary(DictionaryChoice("kanjivg", "local", str(tmp_path)))
    (tmp_path / "0666f.svg").write_text("<svg broken", encoding="utf-8")
    with pytest.raises(ValueError, match="Malformed XML"):
        check_dictionary(DictionaryChoice("kanjivg", "local", str(tmp_path)))


def test_missing_unknown_duplicate_and_invalid_dictionary_settings_are_reported(tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        dictionary_sources((DictionaryChoice("kanjidic2", "local", str(tmp_path / "missing")),))
    with pytest.raises(ValueError, match="Unknown"):
        dictionary_sources((DictionaryChoice("unknown"),))
    with pytest.raises(ValueError, match="Duplicate"):
        dictionary_sources((DictionaryChoice("kanjivg"), DictionaryChoice("kanjivg")))
    with pytest.raises(ValueError, match="choose an XML"):
        dictionary_sources((DictionaryChoice("kanjidic2", "local", str(tmp_path)),))


@pytest.mark.parametrize(
    "entry",
    [
        {"dataset_id": "kanjivg", "mode": "download"},
        {"dataset_id": "kanjivg", "mode": "local"},
        {"dataset_id": "kanjivg", "path": 1},
        {"mode": "bundled"},
    ],
)
def test_invalid_saved_dictionary_choices_are_rejected(entry):
    with pytest.raises(ValueError):
        from_dict({"version": 4, "dictionaries": [entry]})


def test_version_three_migration_preserves_generation_preferences():
    previous = Settings().to_dict()
    previous["version"] = 3
    previous.pop("dictionaries")
    previous["generation"]["production"]["auto_generate"] = False
    settings = from_dict(previous)
    assert settings.dictionaries == ()
    assert not settings.generation_settings("production").auto_generate
    assert dictionary_sources(settings.dictionaries) == {
        key: path
        for key, path in bundled_sources().items()
        if key not in {"school-grades", "joyo", "jlpt-openjlpt"}
    }
