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
        component_entries=lookup_component_entries(kanji, visuals, entries),
        component_kanji=lookup_component_kanji(kanji, strokes, visuals),
    )


def lookup_component_entries(kanji, visuals, known=()):
    """Look up meanings for encoded components that are not already known entries."""
    if kanji is None:
        return ()
    seen = {entry.character for entry in known}
    found = []
    for key in sorted({part for visual in visuals for part in visual.components}):
        if len(key) != 1 or key in seen:
            continue
        entry = kanji.lookup_kanji(key)
        if entry is not None:
            found.append(entry)
    return tuple(found)


def kanji_order(entry):
    """Common, simpler kanji first: school grade, then stroke count."""
    return (entry.grade or 99, entry.stroke_count or 99, entry.character)


def lookup_component_kanji(kanji, strokes, visuals):
    """All dictionary kanji with a meaning that contain each scanned component."""
    index_of = getattr(strokes, "component_index", None)
    if kanji is None or index_of is None:
        return ()
    index = index_of()
    found = []
    for key in sorted({part for visual in visuals for part in visual.components}):
        if len(key) != 1 or key not in index:
            continue
        users = (kanji.lookup_kanji(character) for character in index[key])
        users = sorted((entry for entry in users if entry and entry.meanings), key=kanji_order)
        if users:
            found.append((key, tuple(users)))
    return tuple(found)
