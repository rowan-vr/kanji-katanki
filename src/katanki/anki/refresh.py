"""Read-only refresh planning from saved categories, ownership, and ignored identities."""

from dataclasses import dataclass, replace

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
    if not categories or any(
        item not in ("recognition", "production", "parts") for item in categories
    ):
        raise ValueError("Choose recognition, production, or parts cards.")
    # Manual input selects characters; Jitendex supplies production example words.
    scan = ScanResult(0, tuple(sorted(extract_candidates(text))))
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
    return _prepare_report(collection, settings, report, categories=categories, progress=progress)


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
