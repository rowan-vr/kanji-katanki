"""Plan and apply managed example updates without touching user fields or scheduling."""

import json
import re
from dataclasses import dataclass, replace
from html import escape

from ..dictionaries.manager import DictionaryManager
from ..dictionaries.preferences import dictionary_sources
from ..dictionaries.words import ATTRIBUTION, selected_words
from ..generation.cards import CardContent, normalize_prompt, note_type_spec
from ..generation.examples import STATE_FIELD, encode_state, lines, managed_fields
from ..generation.planner import NOTE_TYPES, Identity
from ..generation.preview import build_preview
from .identities import owned_identities


@dataclass(frozen=True)
class ExampleUpdate:
    note_id: int
    identity: Identity
    before: tuple[tuple[str, str], ...]
    after: tuple[tuple[str, str], ...]
    migration: bool = False


@dataclass(frozen=True)
class ExampleRefreshPlan:
    updates: tuple[ExampleUpdate, ...] = ()
    conflicts: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExampleRefreshResult:
    changes: object
    updated: int
    conflicts: tuple[str, ...]


def plan_example_refresh(collection, report, settings):
    if not settings.refresh.update_examples:
        return ExampleRefreshPlan()
    owned = {}
    for note_type in NOTE_TYPES:
        category = "parts" if note_type.startswith("primitive") else note_type.split("-")[1]
        if settings.card_settings(category).auto_refresh:
            owned.update(owned_identities(collection, note_type=note_type))
    if not owned:
        return ExampleRefreshPlan()
    # Generated notes remain eligible even after their source word disappears.
    entries = {entry.character: entry for entry in report.entries}
    with DictionaryManager(dictionary_sources(settings.dictionaries)) as manager:
        for identity in owned:
            if identity.kind == "kanji" and identity.key not in entries:
                entry = manager.lookup_kanji(identity.key)
                if entry:
                    entries[identity.key] = entry
    expanded = replace(report, entries=tuple(entries.values()))
    word_provider = selected_words(settings.dictionaries)
    preview = build_preview(
        expanded,
        (),
        word_suggestions=word_provider,
        recognition=tuple(i.key for i in owned if i.note_type == "kanji-recognition"),
        production=tuple(i.key for i in owned if i.note_type == "kanji-production"),
        include_primitives=False,
        primitive_recognition=tuple(i.key for i in owned if i.note_type == "primitive-recognition"),
        primitive_production=tuple(i.key for i in owned if i.note_type == "primitive-production"),
        card_settings={
            category: settings.card_settings(category)
            for category in ("recognition", "production", "parts")
        },
    )
    contents = {content.identity: content for content in preview.contents}
    parts_options = settings.card_settings("parts")
    for identity in owned:
        if identity.kind == "primitive":
            contents[identity] = CardContent(
                identity,
                identity.key,
                examples=tuple(
                    sorted(
                        {
                            visual.character
                            for visual in report.strokes
                            if visual.character != identity.key
                            and any(part.key == identity.key for part in visual.component_entries)
                        }
                    )
                ),
                example_limit=parts_options.example_limit,
                show_examples=parts_options.show_examples,
            )
    updates, conflicts = [], []
    # Reserve current production clues, including categories with refresh disabled.
    occupied = {}
    for ids in owned_identities(collection, note_type="kanji-production").values():
        for nid in ids:
            note = collection.get_note(nid)
            occupied.setdefault(normalize_prompt(" ".join(lines(note["Prompt"]))), set()).add(nid)
    proposed = {}
    for identity, ids in sorted(owned.items()):
        label = f"{identity.key} ({identity.note_type})"
        if len(ids) != 1:
            conflicts.append(f"{label}: duplicate owned notes; examples preserved.")
            continue
        note = collection.get_note(ids[0])
        content = contents.get(identity)
        if content is None:
            conflicts.append(f"{label}: dictionary/component data unavailable; examples preserved.")
            continue
        desired = managed_fields(content.fields(), identity)
        desired["Attribution"] = note["Attribution"]
        if (
            any(word not in content.discovered_examples for word in content.examples)
            and identity.kind == "kanji"
        ):
            attribution = escape(getattr(word_provider, "attribution", ATTRIBUTION))
            if attribution not in desired["Attribution"]:
                desired["Attribution"] += "<br>" + attribution
        if identity.note_type == "kanji-production":
            options = settings.card_settings("production")
            words = lines(note["UserExamples"]) if "UserExamples" in note else ()
            words = tuple(dict.fromkeys((*words, *content.examples)))
            shown = words[: options.example_limit] if options.example_limit else words
            if not options.show_examples:
                shown = ()
            meaning = " ".join(lines(note["Meanings"]))
            if not shown or not meaning:
                conflicts.append(f"{label}: empty production clues; current clues preserved.")
                continue
            prompt = "\n".join((meaning, "", *(word.replace(identity.key, "__") for word in shown)))
            desired["Prompt"] = "<br>".join(escape(line) for line in prompt.split("\n"))
        current = {name: note[name] if name in note else "" for name in desired}
        state = None
        if STATE_FIELD in note and note[STATE_FIELD]:
            try:
                recorded = json.loads(note[STATE_FIELD])
                if recorded["version"] != 1 or set(recorded["fields"]) != set(desired):
                    raise ValueError("Unsupported example state")
                state = recorded["fields"]
            except (ValueError, KeyError, TypeError):
                conflicts.append(f"{label}: invalid generated-value record; examples preserved.")
                continue
        if state is not None and current != state:
            conflicts.append(f"{label}: manually edited managed examples; edits preserved.")
            continue
        if state == desired and current == desired:
            continue
        after = dict(desired)
        after[STATE_FIELD] = encode_state(desired)
        if identity.note_type == "kanji-production":
            key = normalize_prompt(" ".join(lines(desired["Prompt"])))
            proposed.setdefault(key, []).append(note.id)
        updates.append(
            ExampleUpdate(
                note.id,
                identity,
                tuple(note.items()),
                tuple(after.items()),
                migration=state is None,
            )
        )
    safe = []
    for update in updates:
        if update.identity.note_type == "kanji-production":
            key = normalize_prompt(" ".join(lines(dict(update.after)["Prompt"])))
            if occupied.get(key, set()) - {update.note_id} or len(proposed[key]) > 1:
                conflicts.append(
                    f"{update.identity.key}: ambiguous production clues; current clues preserved."
                )
                continue
        safe.append(update)
    return ExampleRefreshPlan(tuple(safe), tuple(conflicts))


def apply_example_refresh(collection, plan, *, migrate=False):
    """Revalidate snapshots before any writes and group field/model updates under Undo."""
    updates, conflicts = [], list(plan.conflicts)
    for update in plan.updates:
        if update.migration and not migrate:
            conflicts.append(f"{update.identity.key}: legacy examples need migration review.")
            continue
        note = collection.get_note(update.note_id)
        if tuple(note.items()) != update.before:
            conflicts.append(
                f"{update.identity.key}: note changed since preview; examples preserved."
            )
            continue
        updates.append(update)
    occupied = {}
    for ids in owned_identities(collection, note_type="kanji-production").values():
        for nid in ids:
            note = collection.get_note(nid)
            occupied.setdefault(normalize_prompt(" ".join(lines(note["Prompt"]))), set()).add(nid)
    proposed = {}
    for update in updates:
        if update.identity.note_type == "kanji-production":
            key = normalize_prompt(" ".join(lines(dict(update.after)["Prompt"])))
            proposed.setdefault(key, []).append(update.note_id)
    safe = []
    for update in updates:
        note = collection.get_note(update.note_id)
        if note.note_type().get("katanki_note_type") != update.identity.note_type:
            conflicts.append(f"{update.identity.key}: ownership changed; examples preserved.")
            continue
        if update.identity.note_type == "kanji-production":
            key = normalize_prompt(" ".join(lines(dict(update.after)["Prompt"])))
            if occupied.get(key, set()) - {update.note_id} or len(proposed[key]) > 1:
                conflicts.append(
                    f"{update.identity.key}: production clues now conflict; preserved."
                )
                continue
        safe.append(update)
    updates = safe
    if not updates:
        from anki.collection import OpChanges

        return ExampleRefreshResult(OpChanges(), 0, tuple(conflicts))
    undo = collection.add_custom_undo_entry("Kanji Katanki: refresh examples")
    count = 0
    try:
        for update in updates:
            note = collection.get_note(update.note_id)
            model = note.note_type()
            changed = False
            spec = note_type_spec(update.identity.note_type)
            legacy_back = re.sub(
                r'<div class="katanki-examples".*?</script>\n',
                "",
                spec.back,
                count=1,
                flags=re.DOTALL,
            )
            if len(model["tmpls"]) == 1:
                template = model["tmpls"][0]
                if template["qfmt"] == spec.front and template["afmt"] == legacy_back:
                    template["afmt"] = spec.back
                    changed = True
            for name in (*dict(update.after), "UserExamples"):
                if name not in {field["name"] for field in model["flds"]}:
                    collection.models.add_field(model, collection.models.new_field(name))
                    changed = True
            if changed:
                collection.models.update_dict(model)
                collection.merge_undo_entries(undo)
                note = collection.get_note(update.note_id)
            for name, value in update.after:
                note[name] = value
            collection.update_note(note)
            count += 1
            collection.merge_undo_entries(undo)
    except Exception as error:
        collection.merge_undo_entries(undo)
        raise RuntimeError(
            f"Example refresh stopped after {count} updates. Use Anki Undo to revert, "
            "or run Refresh again to resume safely."
        ) from error
    return ExampleRefreshResult(collection.merge_undo_entries(undo), count, tuple(conflicts))
