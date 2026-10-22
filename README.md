# Kanji Katanki

Offline-first kanji learning for desktop Anki. **Phase 0 complete: bootstrap and Anki integration.**

Kanji Katanki currently adds **Tools → Kanji Katanki → Analyze Collection** and opens a setup
status dialog. It does not scan, generate cards, download dictionaries, or change
notes. See [the implementation specification](docs/SPECIFICATION.md) for planned work.

Inspired by [Migaku Kanji GOD](https://github.com/migaku-official/Migaku-Kanji-Addon).
Kanji Katanki is an independent project and is not affiliated with Migaku.

## Development

Install [uv](https://docs.astral.sh/uv/), then run from the repository root:

```sh
uv sync --locked
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run python scripts/build_addon.py
```

The build produces `dist/kanji-katanki.ankiaddon`, with its entrypoint and manifest at
the archive root. It contains all runtime Python code and requires no development
tools on the end user's machine. Anki provides Python and Qt; do not install `aqt`
into the development environment. Kanji Katanki code is licensed under the
[MIT License](LICENSE). Third-party dataset licensing and redistribution terms
remain to be reviewed separately.

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

Open **Tools → Kanji Katanki → Analyze Collection** to verify the dialog manually.
For an automated real-host smoke test that opens the dialog and exits:

```sh
/usr/bin/python scripts/anki_dev.py --smoke
```

The smoke test creates a disposable temporary profile with a separate process
identity, leaving the persistent development profile alone. It loads the built
archive through Anki's add-on loader, verifies that repeated registration creates
only one menu/command, checks the add-on log file, opens a real Qt dialog, and
checks note/card counts before and after. The temporary profile is removed on exit. It uses Anki's private
`_run` test entrypoint, so the helper may need adjustment with future host releases.

To install the archive manually, launch Anki with the isolated base above, open
**Tools → Add-ons → Install from file**, choose `dist/kanji-katanki.ankiaddon`, then restart
with the same `-b` argument. Packaging follows the
[official Anki add-on instructions](https://docs.ankiweb.net/addons/sharing).

## Compatibility

Development checks run on Python 3.12.14. The installed integration target is
Linux desktop Anki 26.09.3 with Python 3.14.8. Python `>=3.12` is a development
constraint, not a claim of support for every Anki version. Windows/macOS and a
older Anki releases remain unverified. The Phase 0 baseline is Anki 26.09.3 /
Python 3.14.8 on Linux; no lower minimum is claimed. See the local smoke test result
below before relying on host compatibility.

**Smoke result (2026-10-22): passed** on the installed Linux host above using Qt
offscreen. The packaged add-on loaded, repeated registration kept one menu,
the add-on log was written, its menu opened the status dialog, and note/card
counts stayed unchanged. This verifies the host path, not collection
discovery or cross-platform support. The restricted sandbox blocked Qt startup;
the successful check ran outside that sandbox against a disposable temporary
profile only.

## Logging and failure handling

On the verified Anki version, Katanki uses Anki's `addon.katanki` logger hierarchy.
For the persistent development profile, logs are written to
`.anki-test/logs/addons/katanki/katanki.log` and also reach Anki's console. Normal
startup records menu registration; failures record tracebacks and show a warning.
A failure to display the startup warning is logged without aborting add-on loading.

Unit tests cover the status dialog without collection access, missing profiles,
dialog failures, duplicate registration, and bootstrap failures. Host behavior is
verified separately by the smoke test above. Read-only discovery begins in Phase 1.
