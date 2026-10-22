# Default datasets

KANJIDIC2 and KanjiVG are included in the `.ankiaddon` and enabled by default.
Installed users need no separate download, Python environment, or data path.
Select decks, a note type, and fields in **Analyze Collection**, then scan offline.

| Dataset | Bundled snapshot | Contents | Data license |
| --- | --- | --- | --- |
| KANJIDIC2 | 2026-10-22 | 13,108 entries; Japanese on/kun readings, English meanings, grade, primary stroke count | CC BY-SA 4.0 + EDRDG terms |
| KanjiVG | r20260714 | 6,703 canonical non-variant SVG files | CC BY-SA 3.0 |

JMdict is deferred until vocabulary-aware features need it. An unofficial JLPT
source has not been selected. Neither is bundled speculatively.

The current add-on archive is approximately 12 MiB. Compressed defaults live under
`src/katanki/dictionaries/bundled/` and are generated during builds, not committed
to Git. Only `SOURCES.json` and the dataset manifests track URLs, versions, hashes,
and bundle metadata. Original downloads are cached under ignored `data/upstream/`.
The first build needs network access for missing inputs; subsequent builds reuse
verified inputs and generated files. Installed add-ons never download datasets.

## Attribution and licensing

See [third-party notices](../THIRD_PARTY_NOTICES.md). The add-on includes copies of
those notices, the full EDRDG licence statement, KANJIDIC project documentation,
CC BY-SA 4.0 legal text, and KanjiVG's original COPYING and README. **Sources and
licenses…** in the dialog displays attribution and full CC license texts offline.

KANJIDIC2 is copyright James William Breen and the Electronic Dictionary Research
and Development Group. The bundled derivative omits dictionary indexes, SKIP,
Four Corner and De Roo codes, Pinyin, Korean readings, descriptors, non-English
meanings, nanori, and other unused fields. It remains CC BY-SA 4.0; Kanji Katanki's
MIT code license does not replace the data license. See the
[EDRDG terms](https://www.edrdg.org/edrdg/licence.html) and
[KANJIDIC documentation](https://www.edrdg.org/wiki/KANJIDIC_Project.html).

KanjiVG is copyright Ulrich Apel and contributors, under
[CC BY-SA 3.0](https://kanjivg.tagaini.net/). Canonical SVGs are copied byte-for-byte
from the pinned source archive, retaining their copyright/license comments. The
preview is an adaptation: it reconstructs ordered stroke paths and component
labels, removing other elements, styling, and annotations. These adapted visuals
remain CC BY-SA 3.0. See the [SVG format](https://kanjivg.tagaini.net/svg-format.html).

The pinned KanjiVG source contains one known metadata inconsistency for 橅:
`06a45.svg` names its root element 機. The adapter reports it and withholds that
preview; it does not silently change the upstream file. Among the 6,417 bundled
SVGs whose characters also have dictionary entries, 6,416 pass full adapter
validation. Missing/invalid diagrams do not discard the corresponding dictionary
entry or change the collection.

## Maintainer preparation and regular updates

EDRDG's terms require a procedure for regular dictionary updates. Refresh at least
monthly and before releases, then publish reviewed updates through add-on releases:

```sh
uv run python scripts/bundle_datasets.py --refresh
uv run pytest
uv run ruff check .
uv run python scripts/build_addon.py
```

`--refresh` is an explicit maintainer network operation. It downloads the sources
listed in `bundled/SOURCES.json`, records their hashes, prepares derived defaults,
and updates each manifest's bundled version, count, checksum, and notice paths.
It uses HTTPS-only redirects, bounded downloads/XML/ZIP members, and staging before
replacing prepared defaults. It never opens or updates an Anki collection.

Review and commit the changed source lock, manifests, our notices, and code together.
Do not commit downloaded datasets, generated payloads, or copied upstream documents.
Review licensing changes too, and update this document's snapshot/counts and corpus
tests when inputs change. To change the KanjiVG release, edit its pinned URL and
`kanjivg_release` in `SOURCES.json` first.

A normal build downloads only missing/invalid cached inputs, requires the locked
source checksums, and never silently refreshes tracked metadata:

```sh
uv run python scripts/build_addon.py
```

Build with no network access using already prepared data or verified cached inputs:

```sh
uv run python scripts/build_addon.py --offline
```

You can also prepare only the data with `uv run python scripts/bundle_datasets.py`
(or add `--offline` to require cached inputs). Keep the matching cache if you need
to rebuild old snapshots. A changing upstream URL, including KANJIDIC2's live
archive, can stop a clean build when its bytes no longer match the source lock.
Review an explicit `--refresh` in that case; a normal build never accepts new bytes
just because they are newer. Generated checksums must also match the manifests.

Builds validate payloads and license/documentation copies before packaging. CI and
release workflows build before running the full tests; they do not use `--refresh`.
Plain `pytest` on a fresh checkout runs core tests without downloading anything and
skips data-dependent checks until a build has prepared the defaults.

## Later: on-demand downloads

Dataset packs or individual stroke downloads are deferred to the
[Phase 5 roadmap](ROADMAP.md#phase-5--optional-enhancements-post-beta). The eventual
feature needs source-granularity decisions, explicit controls, checked and versioned
local caching, attribution, retry/cancellation, and offline reuse. It is not part of
this build-time bundling change.

## Optional local overrides

The dialog's source fields are optional overrides of the bundled defaults:

- KANJIDIC2: choose the original UTF-8 `.xml` or `.xml.gz` from the
  [official project](https://www.edrdg.org/wiki/KANJIDIC_Project.html).
- KanjiVG: choose an extracted `kanji/` directory from an
  [official release](https://github.com/KanjiVG/kanjivg/releases). Canonical ZIPs
  with hexadecimal SVG filenames at the archive root also work. The combined XML
  release is not supported by this adapter.

For source inspection without dictionaries, uncheck **Use bundled default
dictionaries** and leave the override fields empty. Candidates then remain
unclassified. Choices are session-only, and no provider choice rewrites cards.

The report shows source paths, attribution, license links, bundled versions and
checksums, the KANJIDIC2 creation date and expanded-XML fingerprint, and the hash
of each used SVG. Support means membership in the selected dictionary; it does
not imply common/Jōyō status or validity judgments for unmatched characters.

Local XML is UTF-8 and bounded to 128 MiB expanded for KANJIDIC2 and 1 MiB per SVG.
Entities are rejected and external DTDs are not fetched. ZIP members are read by
exact canonical filename without filesystem extraction, and active/external SVG
content is removed before display.

## Tiny development fixtures

To deliberately override the real defaults with format/UI test data, choose:

- `tests/fixtures/kanjidic2.xml`
- `tests/fixtures/kanjivg/`

These are original synthetic fixtures. Only 景 and 色 have entries; only 景 has a
diagram, consisting of two lines that are **not** a correct stroke diagram for 景.
They are test data, not learning material, and are not shipped in the add-on.

## Verification recorded on 2026-10-22

50 tests pass after preparing the build, including bundled checksums/notices,
full supported stroke-corpus validation, offline default lookups, safe ZIP access, malformed input handling,
failed-refresh preservation, and a packaged-data import in a separate Python
process. The corpus check explicitly records the one upstream mismatch above.
A checkout without generated payloads passed 45 core tests and skipped five
bundle-dependent checks, then rebuilt successfully from verified cached inputs
without changing tracked source locks/manifests; all 50 tests passed afterward.

The real-host smoke test passed on Linux Anki 26.09.3 / Python 3.14.8 with Qt
offscreen. It exercised both fixture overrides and bundled defaults with empty
path fields, rendered their SVGs, and compared every notes/cards/revlog row before
and after. Deck, child-deck, note-type and field filtering, note deduplication,
source fields/tags, scheduling, and IDs were preserved.

Repeat it using the installed Anki's Python:

```sh
/usr/bin/python scripts/anki_dev.py --smoke
```

Fixture notes are created only in a disposable profile before snapshots are taken.
