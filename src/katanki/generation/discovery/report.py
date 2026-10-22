"""Pure classification through normalized provider contracts."""

from ...common.models import DiscoveryReport, KanjiProvider, ScanResult, StrokeProvider


def classify_scan(
    scan: ScanResult,
    kanji: KanjiProvider | None,
    strokes: StrokeProvider | None,
) -> DiscoveryReport:
    entries = []
    visuals = []
    unmatched = []
    warnings = []
    for character in scan.candidates:
        entry = kanji.lookup_kanji(character) if kanji else None
        if entry is None:
            unmatched.append(character)
        else:
            entries.append(entry)
            if strokes:
                try:
                    visual = strokes.lookup_strokes(character)
                    if visual:
                        visuals.append(visual)
                except (ValueError, OSError) as error:
                    warnings.append(f"{character}: stroke data unavailable ({error})")
    return DiscoveryReport(
        scan,
        tuple(entries),
        tuple(visuals),
        tuple(unmatched),
        kanji is not None,
        (),
        tuple(warnings),
    )
