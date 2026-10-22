"""Orchestrate read-only collection access and local dictionary inspection."""

from dataclasses import replace
from pathlib import Path

from ..common.models import DiscoveryReport, ScanSelection
from ..dictionaries.manager import DictionaryManager
from ..generation.discovery import scan_notes
from ..generation.discovery.report import classify_scan
from .collection import selected_notes
from .identities import owned_identities


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
        existing_count = missing_count = None
        if report.dictionary_loaded:
            try:
                existing = owned_identities(collection, note_type="kanji-recognition")
                existing_keys = {identity.key for identity in existing}
                existing_count = sum(entry.character in existing_keys for entry in report.entries)
                missing_count = len(report.entries) - existing_count
                if any(len(ids) > 1 for ids in existing.values()):
                    warnings.append(
                        "Duplicate Katanki recognition notes found; counted once per character."
                    )
            except ValueError as error:
                warnings.append(f"Owned-note counts unavailable: {error}")
        return replace(
            report,
            provenance=manager.source_details(),
            warnings=tuple(warnings),
            existing_owned=existing_count,
            missing_owned=missing_count,
            attribution=manager.card_attribution(),
        )
