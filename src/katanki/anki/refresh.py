"""Read-only refresh planning from saved categories, ownership, and ignored identities."""

from dataclasses import dataclass

from ..common.models import DiscoveryReport
from ..dictionaries.preferences import dictionary_sources
from ..generation.planner import Identity
from ..generation.preview import GenerationPreview
from .analysis import analyze
from .collection import resolve_sources
from .generation import preview_generation
from .ignored import load_ignored


@dataclass(frozen=True)
class RefreshResult:
    report: DiscoveryReport
    preview: GenerationPreview | None
    ignored_count: int


def prepare_refresh(collection, settings):
    ignored = load_ignored(collection)
    report = analyze(
        collection,
        resolve_sources(collection, settings.sources),
        dictionary_sources(settings.dictionaries),
    )
    if not report.entries:
        return RefreshResult(report, None, len(ignored))
    characters = tuple(entry.character for entry in report.entries)

    def selected(mode):
        if not settings.generation_settings(mode).auto_generate:
            return ()
        return tuple(key for key in characters if Identity(f"kanji-{mode}", key) not in ignored)

    parts = settings.generation_settings("parts").auto_generate
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
    )
    return RefreshResult(report, preview, len(ignored))
