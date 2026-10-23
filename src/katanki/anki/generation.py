"""Preview collection ownership and apply only explicitly approved creations.

All mutations use Anki APIs. Existing notes are never updated, removed or moved.
A stale preview may skip newly existing notes, but never adds extra creations.
"""

import re
from dataclasses import dataclass, replace

from ..generation.cards import CSS, normalize_prompt, note_type_spec
from ..generation.destinations import creation_options
from ..generation.discovery import visible_text
from ..generation.examples import STATE_FIELD
from ..generation.preview import GenerationPreview, build_preview
from ..generation.review import exclude_ignored
from .identities import MODEL_MARKER, owned_identities


def preview_generation(
    collection,
    report,
    *,
    generation_settings=None,
    fallback_deck_id=None,
    allow_missing_decks=False,
    ignored=(),
    **choices,
):
    existing = {}
    relevant = set()
    for category in ("recognition", "production"):
        if choices.get(category):
            relevant.add(f"kanji-{category}")
    if choices.get("include_primitives") or choices.get("primitive_recognition"):
        relevant.add("primitive-recognition")
    if choices.get("primitive_production"):
        relevant.add("primitive-production")
    for note_type in sorted(relevant):
        existing.update(owned_identities(collection, note_type=note_type))
    if generation_settings is not None:
        choices["card_settings"] = {
            category: generation_settings.card_settings(category)
            for category in ("recognition", "production", "parts")
        }
    preview = build_preview(report, tuple(existing), **choices)
    warnings = list(preview.warnings)
    for identity, note_ids in existing.items():
        if len(note_ids) > 1:
            warnings.append(
                f"{identity.key} ({identity.note_type}): duplicate owned notes {note_ids}."
            )
    preview = exclude_ignored(preview, ignored)
    _validate_prompts(collection, preview)
    preview = replace(preview, warnings=tuple(warnings))
    if generation_settings is not None:
        preview = replace(
            preview,
            creations=creation_options(
                preview,
                report,
                generation_settings,
                fallback_deck_id,
                allow_missing_decks=allow_missing_decks,
            ),
        )
        for options in preview.creations:
            if (
                options.deck_id is not None
                and collection.decks.get(options.deck_id, default=False) is None
            ):
                raise ValueError("A target deck is missing. Review Generation settings.")
    return preview


def _validate_prompts(collection, preview):
    """Compare generated clues with existing production notes as well as this plan."""
    prompts = {}
    production_types = {
        item.unit.identity.note_type
        for item in preview.plan.items
        if item.outcome == "create" and item.unit.identity.note_type.endswith("production")
    }
    for note_type in sorted(production_types):
        for identity, ids in owned_identities(collection, note_type=note_type).items():
            for note_id in ids:
                note = collection.get_note(note_id)
                if "Prompt" not in note.keys():
                    raise ValueError("A production note type is missing its Prompt field.")
                normalized = normalize_prompt(visible_text(note["Prompt"]))
                prompts.setdefault((note_type, normalized), set()).add(identity.key)
    contents = {content.identity: content for content in preview.contents}
    for item in preview.plan.items:
        if item.outcome != "create" or not item.unit.identity.note_type.endswith("production"):
            continue
        content = contents[item.unit.identity]
        normalized = normalize_prompt(content.prompt)
        key = (content.identity.note_type, normalized)
        if prompts.get(key, set()) - {content.identity.key}:
            raise ValueError(
                f"{content.identity.key}: production prompt already belongs to another note; "
                "use distinguishing source vocabulary or mnemonic names and preview again."
            )
        prompts.setdefault(key, set()).add(content.identity.key)


@dataclass(frozen=True)
class ApplyResult:
    changes: object
    created: int
    skipped: int


def apply_generation(
    collection, preview: GenerationPreview, *, deck_id: int | None = None
) -> ApplyResult:
    """Called only after UI approval of this exact immutable preview and deck."""
    options = {item.identity: item for item in preview.creations}
    _validate_prompts(collection, preview)
    contents = {content.identity: content for content in preview.contents}
    candidates = [item.unit.identity for item in preview.plan.items if item.outcome == "create"]
    if any(identity not in contents for identity in candidates):
        raise ValueError("The approved preview is missing card content.")
    if preview.creations and (
        len(options) != len(preview.creations) or set(options) != set(candidates)
    ):
        raise ValueError("The approved preview is missing or duplicates generation destinations.")
    for identity in candidates:
        target = options[identity].deck_id if options else deck_id
        if (
            type(target) is not int
            or target <= 0
            or collection.decks.get(target, default=False) is None
        ):
            raise ValueError("A destination deck no longer exists. Preview again.")
        if options and any(
            not isinstance(tag, str) or not tag or any(c.isspace() for c in tag)
            for tag in options[identity].tags
        ):
            raise ValueError("The approved preview contains invalid tags.")
    existing = {}
    models = {}
    for note_type in sorted({identity.note_type for identity in candidates}):
        existing.update(owned_identities(collection, note_type=note_type))
        matches = [
            model for model in collection.models.all() if model.get(MODEL_MARKER) == note_type
        ]
        if len(matches) > 1:
            raise ValueError(
                "Multiple registered Katanki note types; resolve this before generation."
            )
        if matches:
            spec = note_type_spec(note_type)
            model = matches[0]
            legacy_fields = set(spec.fields) - {
                "VocabExamples",
                "UserExamples",
                "ExampleLimit",
                STATE_FIELD,
            }
            if not legacy_fields <= {field["name"] for field in model["flds"]}:
                raise ValueError("A Katanki note type is missing required fields. Preview again.")
            if len(model["tmpls"]) != 1:
                raise ValueError("Katanki generation requires one card template per note type.")
            models[note_type] = model
    candidates_to_create = [identity for identity in candidates if identity not in existing]
    if not candidates_to_create:
        from anki.collection import OpChanges

        return ApplyResult(OpChanges(), 0, len(candidates))
    # Validate every content field before beginning any collection mutations.
    fields_by_identity = {
        identity: contents[identity].fields() for identity in candidates_to_create
    }
    undo = collection.add_custom_undo_entry("Kanji Katanki: generate cards")
    created = 0
    try:
        # Add example storage through Anki APIs under the same Undo entry. Keep
        # customized templates intact. Upgrade only our exact previous back template.
        for note_type, model in models.items():
            changed = False
            spec = note_type_spec(note_type)
            legacy_back = re.sub(
                r'<div class="katanki-examples".*?</script>\n',
                "",
                spec.back,
                count=1,
                flags=re.DOTALL,
            )
            template = model["tmpls"][0]
            if template["qfmt"] == spec.front and template["afmt"] == legacy_back:
                template["afmt"] = spec.back
                changed = True
            for name in spec.fields:
                if name not in {field["name"] for field in model["flds"]}:
                    collection.models.add_field(model, collection.models.new_field(name))
                    changed = True
            if changed:
                collection.models.update_dict(model)
                collection.merge_undo_entries(undo)
        for identity in candidates_to_create:
            if identity.note_type not in models:
                spec = note_type_spec(identity.note_type)
                model = collection.models.new(spec.name)
                model[MODEL_MARKER] = spec.key
                model["css"] = CSS
                for name in spec.fields:
                    collection.models.add_field(model, collection.models.new_field(name))
                template = collection.models.new_template(spec.key.split("-")[1].title())
                template["qfmt"], template["afmt"] = spec.front, spec.back
                collection.models.add_template(model, template)
                added = collection.models.add_dict(model)
                # Anki bounds its Undo history. Keep the target alive after every
                # mutation instead of letting a large batch evict the marker.
                collection.merge_undo_entries(undo)
                models[identity.note_type] = collection.models.get(added.id)
            note = collection.new_note(models[identity.note_type])
            for field, value in fields_by_identity[identity].items():
                note[field] = value
            if options:
                note.tags = list(options[identity].tags)
            collection.add_note(note, options[identity].deck_id if options else deck_id)
            created += 1
            collection.merge_undo_entries(undo)
    except Exception as error:
        try:
            collection.merge_undo_entries(undo)
        except Exception as undo_error:
            raise RuntimeError(
                f"Generation stopped after creating {created} notes, and Undo grouping failed "
                f"({undo_error}). Existing notes were preserved. Preview again to safely resume. "
                f"Original failure: {error}"
            ) from error
        raise RuntimeError(
            f"Generation stopped after creating {created} notes. Existing notes were preserved. "
            "Use Anki Undo to revert this operation, or preview again to safely resume."
        ) from error
    changes = collection.merge_undo_entries(undo)
    return ApplyResult(changes, created, len(candidates) - len(candidates_to_create))
