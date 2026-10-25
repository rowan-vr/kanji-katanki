"""Read-only refresh planning from saved categories, ownership, and ignored identities."""

from dataclasses import dataclass, replace

from ..common.characters import is_kanji
from ..common.models import DiscoveryReport, ScanResult
from ..config import load_settings
from ..dictionaries.preferences import dictionary_sources
from ..generation.discovery import extract_candidates, scan_notes
from ..generation.planner import Identity
from ..generation.preview import GenerationPreview
from .analysis import analyze, analyze_scan
from .collection import resolve_sources, selected_notes
from .example_refresh import (
    ExampleRefreshPlan,
    ExampleRefreshResult,
    apply_example_refresh,
    plan_example_refresh,
)
from .generation import preview_generation
from .ignored import load_ignored


@dataclass(frozen=True)
class RefreshResult:
    report: DiscoveryReport
    preview: GenerationPreview | None
    ignored_count: int
    examples: ExampleRefreshPlan = ExampleRefreshPlan()


def prepare_refresh(collection, settings):
    report = analyze(
        collection,
        resolve_sources(collection, settings.sources),
        dictionary_sources(settings.dictionaries),
    )
    examples = plan_example_refresh(collection, report, settings)
    return _prepare_report(collection, settings, report, examples=examples)


def prepare_manual(
    collection, settings, text, *, categories=("recognition", "production", "parts"), progress=None
):
    return prepare_targets(
        collection,
        settings,
        tuple(sorted(extract_candidates(text))),
        categories=categories,
        progress=progress,
        preserve_order=False,
    )


def prepare_targets(
    collection,
    settings,
    characters,
    *,
    categories=("recognition", "production", "parts"),
    progress=None,
    preserve_order=True,
    limit=None,
):
    """Plan explicit list targets in their original order without changing identities."""
    if limit is not None and limit < 1:
        raise ValueError("The kanji amount must be positive.")
    characters = tuple(dict.fromkeys(characters))
    if any(
        not isinstance(char, str) or len(char) != 1 or not is_kanji(char) for char in characters
    ):
        raise ValueError("List targets must be single kanji characters.")
    if not categories or any(
        item not in ("recognition", "production", "parts") for item in categories
    ):
        raise ValueError("Choose recognition, production, or parts cards.")
    if limit is not None and categories == ("parts",):
        characters = characters[:limit]
    # Manual input selects characters; Jitendex supplies production example words.
    scan = ScanResult(0, characters)
    settings = replace(
        settings,
        cards=tuple(
            replace(item, example_source="discovered_and_default") if index == 1 else item
            for index, item in enumerate(settings.cards)
        ),
    )
    if progress:
        progress(f"Loading dictionaries and stroke data for {len(scan.candidates):,} kanji…")
    report = analyze_scan(collection, scan, dictionary_sources(settings.dictionaries))
    if progress:
        progress("Checking existing cards and preparing examples…")
    result = _prepare_report(collection, settings, report, categories=categories, progress=progress)
    if result.preview is None or not preserve_order:
        return result
    # Visit each requested target in list order, retaining dependency-first ordering.
    items = {item.unit.identity: item for item in result.preview.plan.items}
    ordered = []
    done = set()

    def visit(identity):
        if identity in done or identity not in items:
            return
        done.add(identity)
        item = items[identity]
        for prerequisite in item.unit.prerequisites:
            visit(prerequisite)
        ordered.append(item)

    if limit is not None:
        eligible = tuple(
            character
            for character in characters
            if any(
                item.outcome == "create"
                and item.unit.identity.key == character
                and item.unit.identity.note_type in ("kanji-recognition", "kanji-production")
                for item in items.values()
            )
        )
        # Parts-only selections use target order as well.
        characters = (
            eligible if any(c in categories for c in ("recognition", "production")) else characters
        )[:limit]
    for character in characters:
        for category in ("recognition", "production"):
            visit(Identity(f"kanji-{category}", character))
    if limit is None or categories == ("parts",):
        for identity in items:
            visit(identity)
    preview = replace(result.preview, plan=replace(result.preview.plan, items=tuple(ordered)))
    return replace(result, preview=preview)


def _prepare_report(collection, settings, report, *, examples=None, categories=None, progress=None):
    examples = examples or ExampleRefreshPlan()
    ignored = load_ignored(collection)
    if not report.entries:
        return RefreshResult(report, None, len(ignored), examples)
    characters = tuple(entry.character for entry in report.entries)

    def enabled(mode):
        return (
            mode in categories
            if categories is not None
            else settings.generation_settings(mode).auto_generate
        )

    def selected(mode):
        if not enabled(mode):
            return ()
        return tuple(key for key in characters if Identity(f"kanji-{mode}", key) not in ignored)

    parts = enabled("parts")
    component_keys = tuple(
        sorted(
            {
                part.key
                for visual in report.strokes
                for part in visual.component_entries
                if Identity("primitive-recognition", part.key) not in ignored
            }
        )
    )
    preview = preview_generation(
        collection,
        report,
        generation_settings=settings,
        allow_missing_decks=True,
        recognition=selected("recognition"),
        production=selected("production"),
        include_primitives=parts,
        primitive_recognition=component_keys if parts else (),
        ignored=ignored,
        progress=progress,
    )
    return RefreshResult(report, preview, len(ignored), examples)


def apply_refresh_examples(collection, result, settings, *, migrate=False):
    """Reject a scan invalidated by settings/source edits while a review was open."""
    from anki.collection import OpChanges

    if load_settings(collection) != settings:
        return ExampleRefreshResult(OpChanges(), 0, ("Settings changed; run Refresh again.",))
    current = scan_notes(selected_notes(collection, resolve_sources(collection, settings.sources)))
    if current != result.report.scan:
        return ExampleRefreshResult(
            OpChanges(), 0, ("Source vocabulary changed; run Refresh again.",)
        )
    return apply_example_refresh(collection, result.examples, migrate=migrate)
