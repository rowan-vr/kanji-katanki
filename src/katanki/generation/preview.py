"""Turn a discovery snapshot and explicit per-mode choices into a reviewable plan."""

from collections.abc import Mapping
from dataclasses import dataclass

from ..common.models import DiscoveryReport
from .cards import CardContent, normalize_prompt, vocabulary_prompt
from .planner import GenerationPlan, Identity, LearningUnit, plan_generation


@dataclass(frozen=True)
class GenerationPreview:
    plan: GenerationPlan
    contents: tuple[CardContent, ...]
    warnings: tuple[str, ...]


def build_preview(
    report: DiscoveryReport,
    existing: tuple[Identity, ...],
    *,
    recognition: tuple[str, ...],
    production: tuple[str, ...],
    include_primitives: bool,
    component_names: Mapping[str, str] | None = None,
    primitive_recognition: tuple[str, ...] = (),
    primitive_production: tuple[str, ...] = (),
) -> GenerationPreview:
    """Kanji production uses meanings plus blanked words from selected sources.

    Prerequisites generate recognition only. Primitive production and mnemonic
    names remain independent choices. Generated content copies the scan snapshot;
    deleting source vocabulary cannot change existing generated cards.
    """
    component_names = component_names or {}
    entries = {entry.character: entry for entry in report.entries}
    strokes = {entry.character: entry for entry in report.strokes}
    components = {}
    for visual in sorted(report.strokes, key=lambda entry: entry.character):
        for component in visual.component_entries:
            # Pick a deterministic depiction when a component appears in several kanji.
            components.setdefault(component.key, component)
    units = {}
    contents = {}
    warnings = []

    def add_component(key, mode="recognition"):
        identity = Identity(f"primitive-{mode}", key)
        if identity in units:
            return identity
        component = components.get(key)
        if component is None:
            units[identity] = LearningUnit(identity, unavailable_reason="Missing component data.")
            return identity
        # Insert before recursion so the planner, not recursion, diagnoses cycles.
        units[identity] = LearningUnit(identity)
        parents = (
            tuple(add_component(parent) for parent in component.prerequisites)
            if include_primitives
            else ()
        )
        name = component_names.get(key, "").strip()
        label = name or component.label
        reason = ""
        if len(key) != 1 and not name:
            reason = "A mnemonic name is required for this unencoded component."
        prompt = name if mode == "production" else ""
        if mode == "production" and (not name or name == key):
            reason = "Supply a mnemonic name to use as this component's production clue."
        units[identity] = LearningUnit(identity, parents, label, reason)
        contents[identity] = CardContent(
            identity,
            label,
            svg=component.svg,
            components=component.prerequisites,
            prompt=prompt,
            attribution=report.attribution,
        )
        return identity

    selected = [(key, "recognition") for key in sorted(set(recognition))]
    selected += [(key, "production") for key in sorted(set(production))]
    for key, mode in selected:
        identity = Identity(f"kanji-{mode}", key)
        entry = entries.get(key)
        reason = "" if entry else "No supported dictionary entry."
        visual = strokes.get(key)
        parents = ()
        if include_primitives:
            if visual is None:
                reason = "Component prerequisites cannot be assessed without stroke data."
            else:
                parents = tuple(add_component(parent) for parent in visual.prerequisites)
        prompt, examples = "", ()
        if mode == "production" and entry:
            prompt, examples = vocabulary_prompt(key, entry.meanings, report.scan.vocabulary)
            if not entry.meanings:
                reason = "Kanji meaning is unavailable."
            elif not examples:
                reason = "No matching example words in the selected sources."
        units[identity] = LearningUnit(identity, parents, key, reason)
        if entry:
            contents[identity] = CardContent(
                identity,
                key,
                entry.meanings,
                (*entry.on_readings, *entry.kun_readings),
                visual.components if visual else (),
                visual.svg if visual else b"",
                prompt,
                report.attribution,
                examples,
            )
            if visual is None:
                warnings.append(f"{key}: stroke diagram unavailable.")
    for key in sorted(set(primitive_recognition)):
        add_component(key)
    for key in sorted(set(primitive_production)):
        add_component(key, "production")
    prompts = {}
    for content in contents.values():
        if content.identity.note_type.endswith("production") and content.prompt:
            group = (content.identity.note_type, normalize_prompt(content.prompt))
            prompts.setdefault(group, []).append(content.identity)
    for identities in prompts.values():
        if len(identities) > 1:
            for identity in identities:
                unit = units[identity]
                units[identity] = LearningUnit(
                    identity,
                    unit.prerequisites,
                    unit.label,
                    "Identical production clues: use distinguishing source vocabulary or names.",
                )
    plan = plan_generation(
        units.values(),
        existing,
        include_primitives=bool(
            include_primitives or primitive_recognition or primitive_production
        ),
    )
    return GenerationPreview(
        plan, tuple(contents[key] for key in sorted(contents)), tuple(warnings)
    )
