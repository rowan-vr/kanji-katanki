# Kanji Katanki

Offline-first kanji learning for desktop Anki. **Phase 1 POC: read-only kanji discovery.**

Open **Tools → Kanji Katanki → Analyze Collection** to select source decks, one
note type, and vocabulary fields. The read-only report shows distinct candidate
ideographs, dictionary-supported entries, readings/meanings, and available stroke
diagrams using bundled KANJIDIC2 and KanjiVG defaults, offline from first launch.
It does not generate cards or modify source notes. See [the implementation specification](docs/SPECIFICATION.md) for planned work.
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

The build produces `dist/kanji-katanki.ankiaddon`, with its entrypoint and manifest at
the archive root. It contains all runtime Python code and requires no development
tools on the end user's machine. Anki provides Python and Qt; do not install `aqt`
into the development environment. Kanji Katanki code is licensed under the
[MIT License](LICENSE). Bundled dictionary and stroke data have separate
CC BY-SA licenses; see [third-party notices](THIRD_PARTY_NOTICES.md). The current
archive is about 12 MiB and includes dataset versions, checksums, and license copies.
Builds fetch checksum-locked inputs when needed and generate ignored payloads;
dataset binaries are not stored in Git. Use `scripts/build_addon.py --offline` to
require prepared data or verified local cache. A fresh build needs network access;
installed users do not. Tests never download data on their own and skip bundled-data
checks until the first build. See [dataset maintenance](docs/DATASETS.md).

`src/katanki/anki/` owns host integration. Other feature packages will be added as
needed. Anki loads the packaged `__init__.py`. Existing IDE settings are preserved.

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

Open **Tools → Kanji Katanki → Analyze Collection**, select decks and fields
(Ctrl/Cmd-click for multiple selections). The bundled dictionaries are enabled by
default; local paths are optional overrides. Deck selections include subdecks. Click **Scan selected sources**, then select a
character to inspect its details. See [dataset setup and fixtures](docs/DATASETS.md).

If bundled dictionaries are disabled and no local KANJIDIC2 is supplied, candidates
remain unclassified; a missing entry does not mean
an invalid character. Existing/missing Katanki-owned note counts are explicitly
not assessed until Phase 2 introduces stable ownership identities. Each scan uses
one note type; scan other note types separately. Source choices are not persisted yet.
For an automated real-host smoke test that opens the dialog and exits:

```sh
/usr/bin/python scripts/anki_dev.py --smoke
```

The smoke test creates a disposable temporary profile with a separate process
identity, leaving the persistent development profile alone. It loads the built
archive through Anki's add-on loader, verifies that repeated registration creates
only one menu/command, checks the add-on log file, opens a real Qt dialog, and
compares complete notes/cards/revlog snapshots before and after scanning. The temporary profile is removed on exit. It uses Anki's private
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
