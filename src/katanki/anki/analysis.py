"""Orchestrate read-only collection access and local dictionary inspection."""

from dataclasses import replace
from pathlib import Path

from ..common.models import DiscoveryReport, ScanSelection
from ..dictionaries.manager import DictionaryManager
from ..generation.discovery import scan_notes
from ..generation.discovery.report import classify_scan
from .collection import selected_notes


def analyze(
    collection, selection: ScanSelection, sources: dict[str, Path] | None = None
) -> DiscoveryReport:
    scan = scan_notes(selected_notes(collection, selection))
    with DictionaryManager(sources) as manager:
        report = classify_scan(
            scan,
            manager if "kanji" in manager.status() else None,
            manager if "strokes" in manager.status() else None,
        )
        warnings = list(report.warnings)
        if not report.dictionary_loaded:
            warnings.append(
                "KANJIDIC2 not loaded: candidates cannot be classified as supported kanji."
            )
        if "strokes" not in manager.status():
            warnings.append("KanjiVG not loaded: stroke previews are unavailable.")
        return replace(report, provenance=manager.source_details(), warnings=tuple(warnings))
