# Kanji Katanki

Offline-first kanji learning for desktop Anki. **Phase 2: preview and approve independent kanji/component cards.**

Open **Katanki → Analyze Collection** to select source decks, one
note type, and vocabulary fields. The read-only report shows distinct candidate
ideographs, dictionary-supported entries, readings/meanings, and available stroke
diagrams using bundled KANJIDIC2 and KanjiVG defaults, offline from first launch.
Scanning is read-only. Choose **Generate cards…** after scanning to select
recognition notes and opt into production per character or component. Kanji
production shows its meaning and matching source words with the target blanked out. Review the
detailed plan before approving writes. Existing notes, edits and progress are
preserved. See [the implementation specification](docs/SPECIFICATION.md).
Track completed milestones and remaining work in [the roadmap](docs/ROADMAP.md).

Inspired by [Migaku Kanji GOD](https://github.com/migaku-official/Migaku-Kanji-Addon).
Kanji Katanki is an independent project and is not affiliated with Migaku.

## Development

Install [uv](https://docs.astral.sh/uv/), then run from the repository root:

```sh
uv sync --locked
uv run python scripts/build_addon.py
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

To measure line and branch coverage for the add-on and maintenance scripts:

```sh
uv run --locked pytest --cov --cov-report=term-missing --cov-report=html --cov-report=xml
```

Open `htmlcov/index.html` for an interactive report; `coverage.xml` is available
for IDEs and other tools. Generated reports are ignored by Git. No minimum
coverage threshold is enforced. Tests that require bundled data still need a
build first, as described below; coverage does not include the separate Anki
host smoke test.

The build produces `dist/kanji-katanki.ankiaddon`, with its entrypoint and manifest at
the archive root. It contains all runtime Python code and requires no development
tools on the end user's machine. Anki provides Python and Qt; do not install `aqt`
into the development environment. Kanji Katanki code is licensed under the
[MIT License](LICENSE). Bundled dictionary and stroke data have separate
CC BY-SA licenses; see [third-party notices](THIRD_PARTY_NOTICES.md). The current
archive is about 5 MiB and includes dataset versions, checksums, and license copies.
Builds fetch checksum-locked inputs when needed and generate ignored payloads;
dataset binaries are not stored in Git. Use `scripts/build_addon.py --offline` to
require prepared data or verified local cache. A fresh build needs network access;
installed users do not. Tests never download data on their own and skip bundled-data
checks until the first build. See [dataset maintenance](docs/DATASETS.md).

`src/katanki/anki/` owns host integration. Other feature packages will be added as
needed. Anki loads the packaged `__init__.py`. Existing IDE settings are preserved.

### Commit messages

Use `<type>: <short summary>` for commit messages. Write the summary in the
imperative (for example, "add" or "fix"), without a trailing period.

| Prefix | Use for |
| --- | --- |
| `feat:` | New features |
| `fix:` | Bug fixes |
| `docs:` | Documentation changes |
| `refactor:` | Code restructuring without changing behavior |
| `test:` | Adding or updating tests |
| `style:` | Formatting changes without changing behavior |
| `build:` | Build tooling or dependency changes |
| `ci:` | Continuous integration changes |
| `chore:` | Other maintenance |

Examples:

```text
feat: add kanji reading filters
fix: include subdecks when scanning vocabulary
docs: clarify offline dataset setup
```

An optional scope can identify the affected area, such as
`fix(scanner): ignore duplicate vocabulary`. For a breaking change, add `!`
before the colon (for example, `feat(config)!: rename dictionary path settings`)
and explain the migration in the commit body.

## Isolated Anki development profile

Use the Python interpreter that can import your installed Anki and Qt. On this
Linux machine that is `/usr/bin/python` (the uv environment is separate):

```sh
/usr/bin/python scripts/anki_dev.py
ANKI_SINGLE_INSTANCE_KEY=katanki-development anki -b "$PWD/.anki-test" -p "Katanki Development"
```

The helper builds and stages Kanji Katanki into `.anki-test/addons21/katanki`, creates
an isolated **Katanki Development** profile, and disables automatic sync and
update checks there. It refuses an existing base directory without its development
marker. Rerunning refreshes staged add-on code and preserves the test collection.
Close the development Anki instance before running it again. Restart Anki after
refreshing code. `.anki-test/` is ignored by Git and is separate from your normal
Anki data directory. A separate single-instance key keeps launches separate from
your normal Anki process. Do not put personal study data in this test profile.

Open **Katanki → Analyze Collection**, select decks and fields
(Ctrl/Cmd-click for multiple selections). The bundled dictionaries are enabled by
default; local paths are optional overrides. Deck selections include subdecks. Click **Scan selected sources**, then select a
character to inspect its details. See [dataset setup and fixtures](docs/DATASETS.md).

If bundled dictionaries are disabled and no local KANJIDIC2 is supplied, candidates
remain unclassified; a missing entry does not mean
an invalid character. Existing/missing recognition counts are also
not assessed without a dictionary. With a dictionary, they count supported kanji
within the Katanki recognition note type and report damaged ownership metadata. Production is independent. Each scan uses
one note type; scan other note types separately. Source choices are not persisted yet.

### Generate and test cards

In the isolated development profile, scan vocabulary containing `景色`, then:

1. Click **Generate cards…**. Recognition is checked for supported kanji.
2. To practice writing only `景`, check **Production** beside `景`; leave it
   unchecked beside `色`. The front shows its meaning and `__色`, copied from
   the source word `景色`. Recognition and production use
   separate note types, each with one card and native Anki scheduling.
3. Optionally select graphical component prerequisites or use the components tab
   to choose individual recognition/production notes. Give unencoded shapes a
   mnemonic name; component production uses that name as its clue. Names and
   examples apply to new notes only.
4. Select an existing destination deck and click **Preview generation…**. Check
   create/skip/unavailable outcomes and the displayed content. Cancel performs no
   writes. Only **Approve and create … notes** writes to the collection.
5. Review the generated cards. Backs include readings/meanings, components,
   offline stroke diagrams, playback, stroke numbers and dataset attribution.
   Missing diagrams have a text fallback. Names are graphical/mnemonic labels,
   not dictionary-radical classifications.
6. Generate again: existing same-type characters/components are skipped. Delete
   the source `景色` note and rescan: generated notes and progress remain intact.

Kanji production fronts are generated automatically: the kanji's dictionary
meanings plus every distinct matching word from the selected vocabulary fields.
For sources `時間`, `間`, and `真ん中`, production for `時` shows `__間`; production
for `間` shows `時__` and `__`. `真ん中` supplies an example for `中`, not `時` or `間`.
Every occurrence of the target in a word is blanked. HTML, media references, ruby
readings and bracketed furigana are excluded from example words. Select vocabulary
expression fields; no morphological word segmentation of sentences is performed.

No manual production prompt is required. A missing meaning or matching source
word makes production unavailable. Identical generated clues within a note type
are blocked; add distinguishing source vocabulary (or mnemonic names for
components). Prerequisites generate recognition only. Examples are copied when
creating notes and remain available after source deletion. Use **Katanki → Settings… → Discovery** to add multiple vocabulary sources.
Each source selects a deck or wildcard pattern, a note type, and one or more fields.
For example:

| Deck or pattern | Note type | Field |
| --- | --- | --- |
| `*` (all decks) | Japanese (Yomitan) | Expression |
| `Japanese::Vocab` | Basic | Front |

Use **Test discovery** to try the current rows before saving. A read-only background
scan shows matched note counts, unique vocabulary, and kanji candidates in a results
dialog (up to 1,000 entries per list). It uses unsaved edits without saving settings
or generating cards. Kanji candidates are extracted characters; dictionary support
is not checked by this quick test. Empty matches and invalid source rules show
messages to help correct the configuration.

Use **Add source** / **Remove** to manage rows. `*` matches any text; other
characters are literal and matching is case-sensitive. Matching decks include their
subdecks, so `Japanese::*` covers Japanese subdecks. Wildcards pick up new matching
decks on the next scan. Decks selected from the dropdown retain their IDs across
renames; typed names/patterns follow names. Overlapping rules merge selected fields
and count each source note once, even when it has multiple cards.

The **Generation** tab saves the destination deck and component prerequisite
preference. Settings are
versioned and stored in the current collection; they survive restarts. Subdecks are
included at scan time. Analyze Collection starts with the saved sources and still
allows temporary changes. Generation loads the saved destination and component
preference. Production remains opt-in per character/component and every write
requires preview approval. Missing/deleted source references are shown for review;
unsupported settings versions are preserved and reported rather than reset.
Version 1 source settings migrate to version 2 rules without losing deck IDs or preferences.
One-button and automatic refresh remain later Phase 3 work.

Writes are grouped under **Anki Undo**. If a write fails partway through, the error
reports the created count; undo the operation or preview again to resume safely.
Existing notes are never updated automatically, including after changing source vocabulary
or mnemonic names. Recognition counts refresh on your next scan.

Run the critical lifecycle harness against a disposable temporary collection:

```sh
/usr/bin/python scripts/smoke_generation.py
/usr/bin/python scripts/smoke_generation_batch.py
/usr/bin/python scripts/smoke_settings.py
```

For an automated real-host smoke test that opens the dialog and exits:

```sh
/usr/bin/python scripts/anki_dev.py --smoke
```

The smoke test creates a disposable temporary profile with a separate process
identity, leaving the persistent development profile alone. It loads the built
archive through Anki's add-on loader, verifies that repeated registration creates
only one Katanki menu with Analyze Collection and Settings commands, checks the add-on log file, opens a real Qt dialog, and
compares complete notes/cards/revlog snapshots before and after scanning. It then
checks settings Save/Cancel and saved defaults, generation cancellation/approval, all four note types, and stroke playback
and numbering in the real webview. The temporary profile is removed on exit. It uses Anki's private
`_run` test entrypoint, so the helper may need adjustment with future host releases.

To install the archive manually, launch Anki with the isolated base above, open
**Tools → Add-ons → Install from file**, choose `dist/kanji-katanki.ankiaddon`, then restart
with the same `-b` argument. Packaging follows the
[official Anki add-on instructions](https://docs.ankiweb.net/addons/sharing).

## Compatibility

Development checks run on Python 3.12.14. The installed integration target is
Linux desktop Anki 26.09.3 with Python 3.14.8. Python `>=3.12` is a development
constraint, not a claim of support for every Anki version. Windows/macOS and
older Anki releases remain unverified. The Phase 0 baseline is Anki 26.09.3 /
Python 3.14.8 on Linux; no lower minimum is claimed. See the local smoke test result
below before relying on host compatibility.

**Smoke result (2026-10-22): passed** on the installed Linux host above using Qt
offscreen. The packaged add-on scanned fixture vocabulary with deck/note-type/field
filtering and duplicate suppression, displayed dictionary details, rendered its SVG,
and left all notes/cards/revlog rows unchanged. Bundled defaults with empty path fields and missing datasets were also checked.
Menu registration and per-add-on logging passed. The successful check ran outside
the restricted sandbox against a disposable temporary profile only. See
[dataset verification](docs/DATASETS.md#verification-recorded-on-2026-10-22) for the
separate real-upstream format check. Cross-platform host compatibility is unverified.

**Phase 2 verification (2026-10-22): passed** on the same Linux host. A disposable
real collection verified native review history and scheduling preservation after
source deletion, selective production, idempotent reruns, prompt collision checks,
partial-failure recovery and grouped Undo. The packaged Qt-offscreen check verified
Cancel/approval, all four note types, and offline stroke playback/numbering in the
real Anki webview. Human visual review and other platforms remain unverified.

## Logging and failure handling

On the verified Anki version, Katanki uses Anki's `addon.katanki` logger hierarchy.
For the persistent development profile, logs are written to
`.anki-test/logs/addons/katanki/katanki.log` and also reach Anki's console. Normal
startup records menu registration; failures record tracebacks and show a warning.
A failure to display the startup warning is logged without aborting add-on loading.

Unit tests cover discovery/extraction, read-only adapter boundaries, normalized
dictionary lookup, manifest validation, bounded XML handling, missing profiles,
dialog failures, duplicate registration, bootstrap failures, and packaging. Host
behavior and exact collection preservation are verified by the smoke test above.
