# Default datasets

KANJIDIC2, KanjiVG and Jitendex are included in the `.ankiaddon` and enabled by default.
Installed users need no separate download, Python environment, or data path.
Choose sources under **Settings → Discovery**, then use **Refresh** offline.

| Dataset | Bundled snapshot | Contents | Data license |
| --- | --- | --- | --- |
| KANJIDIC2 | 2026-10-23 | 13,108 entries; Japanese on/kun readings, English meanings, grade, primary stroke count | CC BY-SA 4.0 + EDRDG terms |
| KanjiVG | r20260714 | 6,703 canonical non-variant SVG files | CC BY-SA 3.0 |
| Jitendex | 2026.10.03.0 | Complete Yomitan export: 436,555 term rows; 17,126 eligible common word forms | CC BY-SA 4.0; Tatoeba CC BY 2.0 FR; EDRDG terms |

Jitendex 2026.10.03.0 is also bundled in full: the original 38.8 MB Yomitan
archive plus a lightweight CC BY-SA 4.0 suggestion index with 17,126 common
headword/reading/priority rows (about 540 KB before ZIP compression). The complete
add-on stays below 50 MB. JMdict
is included through Jitendex; no separate JMdict archive is needed. An unofficial
JLPT source has not been selected.

Jitendex now participates in the shared dictionary update catalog, validation,
installation and bundled-fallback machinery. Settings → Dictionaries exposes
Default, local Yomitan ZIP, Disabled, Check dictionary, Update dictionary, and Use
bundled version. Disabling it removes dictionary defaults without removing the
user's discovered vocabulary. Local overrides take precedence over installed
updates. Selection affects subsequent generation/Refresh, never rewrites notes
just by changing a dictionary choice.

All three datasets use the same release-pack system:

- Normal builds fetch only the immutable release assets pinned in
  `datasets/bundled-lock.json` and verify pack and file checksums.
- Installed add-ons consult `datasets/catalog.json` for compatible releases,
  then download and validate the selected pack before activating it atomically.
- Bundled payloads live together under `dictionaries/bundled/`:
  `kanjidic2.xml`, `kanjivg.zip`, and `jitendex.zip`.
- Maintainer preparation uses the shared `bundled/SOURCES.json` provenance and
  `scripts/bundle_datasets.py`. There is no separate Jitendex lock, folder or
  normal-build upstream download route.

Jitendex's original Yomitan archive is retained byte-for-byte, including all
436,555 term rows. The adapter compiles the 17,126 eligible common word forms on
first use and caches them in memory by source path, size and modification time.
Bundled, installed and local sources use the same reader and ranking rules.
Changing a source does not modify user dictionaries or fetch data during review.
See [card examples](CARD_EXAMPLES.md#default-words) for ranking.

Jitendex is © Stephen Kraus, under CC BY-SA 4.0, and includes JMdict © EDRDG.
The source attribution, EDRDG terms, CC BY-SA 4.0 and Tatoeba CC BY 2.0 FR license
texts are included under `bundled/licenses/`, with the shared `bundled/NOTICE.txt`.
The full archive preserves definitions, examples, ruby markup, images, metadata
and embedded Hanazono/GlyphWiki font licenses. Only the in-memory suggestion list
filters entries; the bundled dictionary is complete.

### First combined release

The combined baseline is published as
[datasets-2026-10-23-jitendex](https://github.com/rowan-vr/kanji-katanki/releases/tag/datasets-2026-10-23-jitendex).
All three archives and the matching catalog have been downloaded and verified
against the checked-in build lock. Their local copies remain in `dist/datasets/`.
This is a dataset-only prerelease; the stable add-on release is unchanged.

Publication used the following command (the existing assets must not be replaced):

```sh
gh release create datasets-2026-10-23-jitendex \
  dist/datasets/kanjidic2.zip dist/datasets/kanjivg.zip \
  dist/datasets/jitendex.zip dist/datasets/catalog.json \
  --repo rowan-vr/kanji-katanki --prerelease \
  --title 'Dictionary packs: Jitendex integration'
```

Cold builds can now fetch all three packs from this release using the shared build
lock; verified caches also support offline rebuilds. The matching catalog and
integration changes still need to be merged to advertise Jitendex through the
public runtime catalog on main. Later releases use the same monthly/manual
Dataset packs workflow and reviewed catalog promotion as before.

The add-on archive is approximately 44 MB and includes offline defaults. Dataset
payloads and copied upstream notices stay out of Git. Versioned packs live as
GitHub Release assets in this same repository, under `datasets-…` tags.

Two small files serve separate purposes:

- `datasets/bundled-lock.json` pins the exact pack URLs, SHA-256 hashes, sizes and
  versions used by this code revision. Normal builds never consult changing
  upstream files or the latest update catalog.
- `datasets/catalog.json` advertises the latest compatible packs for installed
  users. The add-on checks the `main` branch copy over HTTPS. Updating this file
  does not require an add-on release.

Builds restore all three ignored runtime payloads under
`src/katanki/dictionaries/bundled/` from those packs. Verified pack downloads are
cached by hash under ignored `data/packs/`. Original maintainer downloads are
cached under ignored `data/upstream/`. Canonical XML and inner SVG ZIP members
remain uncompressed to keep their locked checksums portable; release packs and
the final add-on archive compress these assets.

## User updates and offline fallback

Settings → Dictionaries offers **Check for dictionary updates**, per-dataset
**Update dictionary**, and **Use bundled version**. The default source uses a
verified compatible downloaded update when it is newer than the bundled version;
otherwise it uses bundled data. Local overrides and Disabled retain their meaning.
A newer add-on's bundled version supersedes older downloaded data automatically.

Downloads and returning to bundled data apply immediately to future lookups; they
do not rewrite existing notes, source settings, or review history. These actions
are independent of the Settings Save/Cancel buttons. **Check daily on startup** is
opt-in and saved with Settings; checks run in the background at most once daily
per add-on installation and download only the small catalog. Updates require a
button press. Last successful check, active version and available version appear
in Settings. Offline startup never requires a check.

Updates are stored in Anki's preserved `user_files/dictionaries/` directory,
outside packaged defaults. Packs carry their attribution and license notices,
visible in Settings. An update is staged, bounded, hash-checked, parsed and
validated before its active pointer is replaced atomically. Failed downloads or
activation preserve working data. Damaged installed files fall back to bundled
defaults. Prior installed packs are retained on disk; returning to bundled data
only deactivates the downloaded copy. Pack files are data, never executable code.

The catalog and hosting repository are the trust boundary. A pack hash identifies
its published bytes; it does not independently authenticate the upstream author.
Use available upstream checksums during preparation and review licensing/provenance.

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

Prepare reviewed updates at least monthly and before releases. The separate
**Dataset packs** workflow runs monthly to produce candidate artifacts; manual
runs can also publish packs as a dataset prerelease. Scheduled runs do not publish
or promote the public catalog. Publishing runs only from `main`, in a separate
job with write permission. Dataset prereleases do not trigger the add-on release
job or replace the latest stable add-on release.

The workflow artifact includes all three packs (`kanjidic2.zip`, `kanjivg.zip`,
`jitendex.zip`), candidate `catalog.json`, and a
`review/` directory containing the shared source provenance and manifests. Pack preparation
round-trips each candidate through the same validator used by installed clients.
Upstream/format failures affect this maintenance workflow, not normal CI.

To prepare locally:

```sh
uv run python scripts/dataset_packs.py --refresh --tag datasets-YYYY-MM-DD-unique
```

This explicit refresh fetches official sources, normalizes defaults, updates the
source lock/manifests, and writes packs plus review metadata to `dist/datasets/`.
Choose a new tag every time; never replace a published asset. To change KanjiVG,
edit the pinned URL and `kanjivg_release` in `bundled/SOURCES.json` first. The raw
source lock is preparation provenance, not the normal build's download target.

Publish packs before promoting their catalog. The older two-dictionary baseline was published under `datasets-2026-10-23`.
The initial publishing command was:

```sh
gh release create datasets-2026-10-23 \
  dist/datasets/kanjidic2.zip dist/datasets/kanjivg.zip dist/datasets/catalog.json \
  --repo rowan-vr/kanji-katanki --prerelease \
  --title 'Dictionary packs 2026-10-23' \
  --notes 'Offline defaults and independent dictionary updates; license notices included.'
```

The original two-pack release remains available for older commits. The new
three-pack baseline is published as described above; prepared defaults and the
verified pack cache also support offline builds.

After checking published assets, review and promote `datasets/catalog.json` to
advertise updates. For a new bundled baseline, also copy that catalog to
`datasets/bundled-lock.json` and commit matching source locks/manifests from
`review/` together. Review notice changes, counts and corpus-test expectations.
To advertise only compatible runtime updates, change the public catalog without
changing the older bundled lock or its manifests. Keep old packs available so
older commits can rebuild and existing compatible clients can download them.

Run the normal build/tests after baseline changes:

```sh
uv run python scripts/build_addon.py
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Normal builds fetch only immutable release pack URLs from the committed build
lock, verify pack/file hashes, metadata and licenses, and check derived payloads
against the manifests. They never update locks. `scripts/bundle_datasets.py`
restores the locked packs without packaging the add-on; `--refresh` remains a
maintainer-only raw-source preparation operation.

Use `scripts/build_addon.py --offline` or `scripts/bundle_datasets.py --offline`
to require existing prepared defaults or verified pack cache. A cold build needs
GitHub, while installed users already have their offline defaults. Plain unit
tests never download data; bundle-dependent checks skip until a build prepares it.

## Later: additional on-demand assets

Independent updates for all three default dictionaries are implemented. Additional
providers and per-character downloads remain deferred; review flows must continue
working without network access.

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

## Verification recorded on 2026-10-23

150 unit/packaging tests pass, including failed updates, source precedence,
corrupt-file fallback, incompatible catalogs, exact locked pack downloads,
offline rebuilds, and exclusion of persistent user data from packaged add-ons.
Lint and formatting checks pass. The real Anki/Qt smoke test passes with a
disposable profile and mocked network responses: update checks and installation
run asynchronously, active license notices change with the pack, returning to
bundled data works, offline checks preserve defaults, and Cancel does not save
automatic-check preferences. Existing generation and collection-preservation
checks pass too. Initial release packs are prepared locally and hash-checked
against both catalogs. The published October 23 prerelease has been downloaded
and verified against the refreshed manifests and source provenance.

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


## Jitendex integration verification, 2026-10-23

251 unit/packaging tests pass, including local selection in generation and Refresh,
disabled defaults, same-day revision ordering, downloaded activation and bundled
fallback, malformed ZIP/term rejection, changed-source caches, and maintainer
source-lock regeneration. The full three-pack candidate was generated offline and
round-tripped through the installed-client validator. The Jitendex pack is about
38.9 MB and carries the original export plus self-contained license notices.
Real Anki/Qt checks cover list visibility, local ZIP checks, saved choices,
update dialogs, installation, disabled mode, returning to bundled data and offline
failure. Host baseline: Linux Anki 26.09.3 / Python 3.14.8. The three packs and
matching catalog were subsequently published as the dataset-only prerelease
`datasets-2026-10-23-jitendex`, downloaded again, and verified against the build lock.
