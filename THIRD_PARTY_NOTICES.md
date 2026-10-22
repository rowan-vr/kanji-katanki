# Third-party dataset notices

Kanji Katanki's Python code is MIT licensed. The following bundled datasets have
separate licenses; they are not relicensed under MIT. No endorsement by their
creators is implied. Versions, source URLs, checksums, and entry counts are
recorded in `dictionaries/manifests/` and `dictionaries/bundled/SOURCES.json`
inside the installed add-on.

## KANJIDIC2 — CC BY-SA 4.0

This package uses KANJIDIC2, copyright James William Breen and the Electronic
Dictionary Research and Development Group (EDRDG).

Source and documentation: https://www.edrdg.org/wiki/KANJIDIC_Project.html
Original download: https://www.edrdg.org/kanjidic/kanjidic2.xml.gz
EDRDG terms: https://www.edrdg.org/edrdg/licence.html
License: https://creativecommons.org/licenses/by-sa/4.0/

The bundled derivative retains each character's literal, Japanese on/kun readings,
English meanings, school grade, and primary stroke count. XML is regenerated and
gzip-compressed. All other fields are omitted, including third-party dictionary
indexes, SKIP/Four Corner/De Roo codes, Pinyin, Korean readings, descriptors,
non-English meanings, and nanori. It remains CC BY-SA 4.0, including any rights in
our selection/arrangement. This does not remove upstream ownership or notices.

Copies of the full EDRDG licence statement, KANJIDIC project documentation, and
CC BY-SA 4.0 legal text are in `dictionaries/bundled/licenses/`.

Maintain the data regularly: run `python scripts/bundle_datasets.py --refresh`
at least monthly and before releases, review the generated changes, run tests,
and distribute updated add-on versions. Users may select a newer local
KANJIDIC2 file in Analyze Collection without a network-required review flow.

## KanjiVG — CC BY-SA 3.0

KanjiVG is copyright Ulrich Apel and contributors.

Project: https://kanjivg.tagaini.net/
Source/release: https://github.com/KanjiVG/kanjivg/releases/tag/r20260714
License: https://creativecommons.org/licenses/by-sa/3.0/

Canonical non-variant SVG files are repackaged in a ZIP with their original
contents and copyright/license comments unchanged. Variant SVGs and unrelated
source files are omitted. The runtime preview adapts the selected SVG to ordered
stroke paths and graphical component labels, removing other SVG elements and
styling. Those adapted visuals remain available under CC BY-SA 3.0.

The original COPYING license text and README are included in
`dictionaries/bundled/licenses/`. Missing diagrams are reported as unavailable;
no coverage beyond the supplied data is implied. In the pinned r20260714 source,
06a45.svg (橅) identifies its root element as 機. The adapter reports that metadata
mismatch and withholds the preview; the upstream file is not silently corrected.

## Generated cards

Generated notes copy the selected readings/meanings and embed adapted SVG stroke
paths/component diagrams. Their backs retain the respective dataset attribution,
source and license links, version information, and modification disclosure.
KANJIDIC2-derived content remains CC BY-SA 4.0; KanjiVG-derived diagrams remain
CC BY-SA 3.0. Keep those notices and applicable licenses when sharing exported
notes/decks. Generated diagrams remove original SVG styling and metadata and
add optional playback and stroke-number controls; the data is not relicensed MIT.

## Disclaimer

The datasets and adapted data/visuals are supplied without warranties. See their
full license texts and EDRDG licence statement for the applicable disclaimers,
conditions, and limitations. The MIT code license does not supersede them.
