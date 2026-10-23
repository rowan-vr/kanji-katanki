"""Snapshot destinations and copied tags for explicit approval before creation."""

import re
from dataclasses import dataclass

from ..config import GenerationSettings
from .planner import Identity


@dataclass(frozen=True)
class CreationOptions:
    identity: Identity
    deck_id: int | None
    tags: tuple[str, ...] = ()


def generated_tags(settings: GenerationSettings, source_tags: tuple[str, ...]) -> tuple[str, ...]:
    tags = list(settings.default_tags)
    if settings.copy_source_tags:
        patterns = [
            re.compile(re.escape(pattern).replace(r"\*", ".*"))
            for pattern in settings.source_tag_patterns
        ]
        tags.extend(
            tag
            for tag in source_tags
            if not patterns or any(pattern.fullmatch(tag) for pattern in patterns)
        )
    unique = {}
    for tag in tags:
        unique.setdefault(tag.casefold(), tag)
    return tuple(unique.values())


def creation_options(preview, report, settings, fallback_deck_id, *, allow_missing_decks=False):
    tags_by_key = {key: set(tags) for key, tags in report.scan.character_tags}
    part_tags = {}
    for visual in report.strokes:
        source_tags = tags_by_key.get(visual.character, set())
        graph = {part.key: part.prerequisites for part in visual.component_entries}
        pending = list(visual.prerequisites)
        seen = set()
        while pending:
            key = pending.pop()
            if key in seen:
                continue
            seen.add(key)
            part_tags.setdefault(key, set()).update(source_tags)
            pending.extend(graph.get(key, ()))
    result = []
    for item in preview.plan.items:
        if item.outcome != "create":
            continue
        identity = item.unit.identity
        category = "parts" if identity.kind == "primitive" else identity.note_type.split("-")[1]
        preferences = settings.generation_settings(category)
        deck_id = preferences.target_deck_id or fallback_deck_id
        if deck_id is None and not allow_missing_decks:
            raise ValueError(f"Choose a target deck for {category} in Settings or a fallback deck.")
        source_tags = (part_tags if identity.kind == "primitive" else tags_by_key).get(
            identity.key, ()
        )
        result.append(
            CreationOptions(
                identity, deck_id, generated_tags(preferences, tuple(sorted(source_tags)))
            )
        )
    return tuple(result)
