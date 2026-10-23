"""Select review candidates without adding creations or losing prerequisites."""

import re
from dataclasses import replace

from .cards import note_type_spec
from .planner import GenerationPlan, PlanItem


def category_for(identity):
    return "parts" if identity.kind == "primitive" else identity.note_type.split("-")[1]


def exclude_ignored(preview, ignored):
    unavailable = set()
    items = []
    for item in preview.plan.items:
        identity = item.unit.identity
        if item.outcome == "skip":
            pass  # Existing prerequisites remain satisfied regardless of saved ignore choices.
        elif identity in ignored:
            item = PlanItem(
                item.unit, "unavailable", "Ignored; restore in Settings → Ignored cards."
            )
        elif any(parent in unavailable for parent in item.unit.prerequisites):
            item = PlanItem(item.unit, "unavailable", "A prerequisite is ignored or unavailable.")
        if item.outcome == "unavailable":
            unavailable.add(identity)
        items.append(item)
    creating = {item.unit.identity for item in items if item.outcome == "create"}
    return replace(
        preview,
        plan=GenerationPlan(tuple(items)),
        creations=tuple(item for item in preview.creations if item.identity in creating),
    )


def render_card_preview(content):
    """Render our simple card templates without creating temporary Anki notes."""
    spec = note_type_spec(content.identity.note_type)
    fields = content.fields()
    token = re.compile(r"{{([A-Za-z]+)}}")
    front = token.sub(lambda match: fields.get(match[1], ""), spec.front)
    fields["FrontSide"] = front
    back = token.sub(lambda match: fields.get(match[1], ""), spec.back)
    return front, back
