"""Refresh owned-note examples, dictionary content and tags without changing scheduling."""

from copy import deepcopy
from dataclasses import dataclass, replace
from html import escape

from ..dictionaries.manager import DictionaryManager
from ..dictionaries.preferences import dictionary_sources
from ..dictionaries.words import ATTRIBUTION, WordSuggestions, selected_words
from ..generation.cards import CardContent, normalize_prompt, note_type_spec
from ..generation.destinations import creation_options
from ..generation.examples import (
    STATE_FIELD,
    encode_state,
    lines,
    managed_fields,
    words_for_side,
)
from ..generation.planner import NOTE_TYPES, Identity
from ..generation.preview import build_preview
from ..generation.template_updates import upgrade_stock_layout
from .identities import owned_identities


@dataclass(frozen=True)
class ExampleUpdate:
    note_id: int
    identity: Identity
    before: tuple[tuple[str, str], ...]
    after: tuple[tuple[str, str], ...]
    migration: bool = False
    tags_before: tuple[str, ...] | None = None
    tags_after: tuple[str, ...] | None = None
    migration_reason: str = ""


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
    if not any(
        (
            settings.refresh.update_examples,
            settings.refresh.update_source_tags,
            settings.refresh.update_dictionary_data,
        )
    ):
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
    strokes = {visual.character: visual for visual in report.strokes}
    if settings.refresh.update_dictionary_data:
        with DictionaryManager(dictionary_sources(settings.dictionaries)) as manager:
            for identity in owned:
                if identity.kind == "kanji" and identity.key not in strokes:
                    visual = manager.lookup_strokes(identity.key)
                    if visual:
                        strokes[identity.key] = visual
    expanded = replace(report, entries=tuple(entries.values()), strokes=tuple(strokes.values()))
    word_provider = (
        selected_words(settings.dictionaries)
        if settings.refresh.update_examples
        else WordSuggestions(())
    )
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
    tag_options = {
        option.identity: option.tags
        for option in creation_options(preview, report, settings, None, allow_missing_decks=True)
    }
    parts_options = settings.card_settings("parts")
    for identity in owned:
        if identity.kind == "primitive" and not settings.refresh.update_dictionary_data:
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
        if content is None and (
            settings.refresh.update_examples or settings.refresh.update_dictionary_data
        ):
            conflicts.append(f"{label}: dictionary/component data unavailable; examples preserved.")
            continue
        desired = managed_fields(content.fields() if content else dict(note.items()), identity)
        if not settings.refresh.update_examples:
            desired = {name: note[name] if name in note else "" for name in desired}
        desired["Attribution"] = note["Attribution"]
        if (
            settings.refresh.update_examples
            and any(word not in content.discovered_examples for word in content.examples)
            and identity.kind == "kanji"
        ):
            attribution = escape(getattr(word_provider, "attribution", ATTRIBUTION))
            if attribution not in desired["Attribution"]:
                desired["Attribution"] += "<br>" + attribution
        if identity.note_type == "kanji-production" and (
            settings.refresh.update_examples or settings.refresh.update_dictionary_data
        ):
            options = settings.card_settings("production")
            words = lines(note["UserExamples"]) if "UserExamples" in note else ()
            examples = (
                (content.front_examples if content.front_examples is not None else content.examples)
                if settings.refresh.update_examples
                else words_for_side(note["VocabExamples"], "front")
                if "VocabExamples" in note
                else ()
            )
            words = tuple(dict.fromkeys((*words, *examples)))
            shown = words[: options.example_limit] if options.example_limit else words
            if not options.show_examples:
                shown = ()
            meaning = (
                ", ".join(content.meanings)
                if settings.refresh.update_dictionary_data
                else " ".join(lines(note["Meanings"]))
            )
            if not meaning or (options.show_examples and not shown):
                conflicts.append(f"{label}: empty production clues; current clues preserved.")
                continue
            prompt = (
                "\n".join((meaning, "", *(word.replace(identity.key, "__") for word in shown)))
                if shown
                else meaning
            )
            desired["Prompt"] = "<br>".join(escape(line) for line in prompt.split("\n"))
        # These fields belong to Katanki. Refresh regenerates them even when
        # Anki's HTML editor or a manual edit changed the recorded values.
        after = dict(desired) if settings.refresh.update_examples else {}
        if settings.refresh.update_dictionary_data:
            fields = content.fields()
            for name in ("Meanings", "Readings", "Components", "Strokes"):
                # Missing optional stroke data must not erase a working diagram.
                if name == "Strokes" and not content.svg:
                    continue
                after[name] = fields[name]
            after["Attribution"] = "<br>".join(
                dict.fromkeys(
                    (*note["Attribution"].split("<br>"), *fields["Attribution"].split("<br>"))
                )
            )
            desired["Attribution"] = after["Attribution"]
            if identity.note_type == "kanji-production":
                after["Prompt"] = desired["Prompt"]
        if settings.refresh.update_examples or settings.refresh.update_dictionary_data:
            after[STATE_FIELD] = encode_state(desired)
        tags_before = tags_after = None
        if settings.refresh.update_source_tags:
            tags_before = tuple(note.tags)
            tags = {tag.casefold(): tag for tag in tags_before}
            for tag in tag_options.get(identity, ()):
                tags.setdefault(tag.casefold(), tag)
            tags_after = tuple(tags.values())
        if (
            all(name in note and note[name] == value for name, value in after.items())
            and tags_before == tags_after
        ):
            if not settings.refresh.update_examples or not upgrade_stock_layout(
                deepcopy(note.note_type()), identity.note_type
            ):
                continue
        if identity.note_type == "kanji-production":
            key = normalize_prompt(" ".join(lines(desired["Prompt"])))
            proposed.setdefault(key, []).append(note.id)
        updates.append(
            ExampleUpdate(
                note.id,
                identity,
                tuple(note.items()),
                tuple(after.items()),
                tags_before=tags_before,
                tags_after=tags_after,
            )
        )
    safe = []
    for update in updates:
        if update.identity.note_type == "kanji-production":
            key = normalize_prompt(
                " ".join(lines(dict(update.after).get("Prompt", dict(update.before)["Prompt"])))
            )
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
            conflicts.append(
                f"{update.identity.key} ({update.identity.note_type}): "
                "example change tracking needs replacement review; "
                "run manual Refresh to review a repair. Current fields preserved."
            )
            continue
        note = collection.get_note(update.note_id)
        if tuple(note.items()) != update.before or (
            update.tags_before is not None and tuple(note.tags) != update.tags_before
        ):
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
            key = normalize_prompt(
                " ".join(lines(dict(update.after).get("Prompt", dict(update.before)["Prompt"])))
            )
            proposed.setdefault(key, []).append(update.note_id)
    safe = []
    for update in updates:
        note = collection.get_note(update.note_id)
        identity_field = note_type_spec(update.identity.note_type).fields[0]
        if (
            note.note_type().get("katanki_note_type") != update.identity.note_type
            or note[identity_field] != update.identity.key
        ):
            conflicts.append(f"{update.identity.key}: ownership changed; examples preserved.")
            continue
        if update.identity.note_type == "kanji-production":
            key = normalize_prompt(
                " ".join(lines(dict(update.after).get("Prompt", dict(update.before)["Prompt"])))
            )
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
            changed = upgrade_stock_layout(model, update.identity.note_type)
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
            if update.tags_after is not None:
                note.tags = list(update.tags_after)
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
