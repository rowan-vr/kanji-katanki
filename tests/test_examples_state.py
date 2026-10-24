"""Change-tracking records must survive Anki's HTML note editor unchanged."""

import json

import pytest

from katanki.generation.examples import UnsupportedStateVersion, decode_state, encode_state


def test_baseline_escapes_markup_and_entities_without_changing_decoded_values():
    fields = {
        "VocabExamples": '<div data-source="vocabulary" data-status="new">一度</div>',
        "Prompt": 'one &lt;two&gt;<br>__度 "quoted" \\ slash',
        "Attribution": 'Copyright A &amp; B — 日本語 <a href="https://example.org">Source</a>',
        "ExampleLimit": "5",
    }
    encoded = encode_state(fields)
    assert not any(mark in encoded for mark in "<>&")
    assert r"\u003cdiv" in encoded
    assert decode_state(encoded, fields) == fields


def test_valid_legacy_json_remains_readable_and_upgrades_without_losing_values():
    fields = {"VocabExamples": '<div data-source="vocabulary">一度</div>'}
    legacy = json.dumps({"version": 1, "fields": fields}, ensure_ascii=False)
    assert decode_state(legacy, fields) == fields
    assert decode_state(encode_state(decode_state(legacy, fields)), fields) == fields


@pytest.mark.parametrize(
    "value",
    [
        "null",
        "[]",
        '"text"',
        "{}",
        '{"version": true, "fields": {"Prompt": "x"}}',
        '{"version": 1, "fields": []}',
        '{"version": 1, "fields": {}}',
        '{"version": 1, "fields": {"Prompt": null}}',
        '{"version": 1, "fields": {"Prompt": ["x"]}}',
    ],
)
def test_malformed_baseline_shapes_are_rejected_before_comparing_fields(value):
    with pytest.raises(ValueError):
        decode_state(value, ("Prompt",))


def test_newer_baselines_are_distinguished_from_editor_damage():
    with pytest.raises(UnsupportedStateVersion):
        decode_state('{"version": 2, "fields": {"Prompt": "x"}}', ("Prompt",))


def editor_damaged_state(fields):
    """The exact attribute representation observed in the affected saved notes."""
    raw = json.dumps({"version": 1, "fields": fields}, ensure_ascii=False)
    for name, values in (
        ("data-source", ("vocabulary", "default", "components")),
        ("data-status", ("learned", "relearning", "learning", "new", "exists", "missing")),
    ):
        for value in values:
            raw = raw.replace(
                name + r"=\"" + value + r"\"", name + r'="\&quot;' + value + r'\&quot;"'
            )
    return raw


@pytest.mark.parametrize(
    "status", ("learned", "relearning", "learning", "new", "exists", "missing")
)
def test_recovers_exact_old_attribute_escapes_without_using_current_values(status):
    from katanki.generation.examples import recover_editor_state

    original = {
        "VocabExamples": f'<div data-source="vocabulary" data-status="{status}">丈夫</div>',
        "ExampleLimit": "3",
        "Attribution": "Source",
        "Prompt": "husband<br><br>丈__",
    }
    damaged = editor_damaged_state(original)
    with pytest.raises(ValueError):
        decode_state(damaged, original)
    assert recover_editor_state(damaged, original.keys()) == original


def test_unrecognized_damage_and_schema_changes_are_not_guessed():
    from katanki.generation.examples import recover_editor_state

    with pytest.raises(ValueError):
        recover_editor_state("damaged", ("Prompt",))
    damaged = editor_damaged_state({"VocabExamples": '<div data-source="vocabulary">丈夫</div>'})
    with pytest.raises(ValueError):
        recover_editor_state(damaged, ("VocabExamples", "Prompt"))
    with pytest.raises(UnsupportedStateVersion):
        recover_editor_state(damaged.replace('"version": 1', '"version": 2'), ("VocabExamples",))
