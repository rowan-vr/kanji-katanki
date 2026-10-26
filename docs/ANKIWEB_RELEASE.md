# AnkiWeb upload — 0.1.0 public beta

## Upload fields

- Title: **Kanji Katanki — Japanese Kanji Cards & Statistics**
- Archive: `dist/kanji-katanki.ankiaddon`
- Description: paste the HTML from [ANKIWEB_DESCRIPTION.html](ANKIWEB_DESCRIPTION.html).
- Support URL: https://github.com/rowan-vr/kanji-katanki/issues
- Source URL: https://github.com/rowan-vr/kanji-katanki
- Code license: MIT; bundled datasets retain their separate licenses.
- Tested version: Anki 26.09.3, Linux, Python 3.14.8.
  Do not claim older-version or Windows/macOS verification. If the form asks
  for a minimum version, 26.09.3 is the conservative initial beta baseline;
  this is not evidence that older releases are incompatible.

Upload through https://ankiweb.net/shared/upload while signed into the intended
publisher account. Review the rendered description before submitting. The archive
is approximately 43 MiB; acceptance by AnkiWeb has not yet been verified.

## Preparation recorded on 2026-10-26

- Offline build succeeded; archive CRC, root entrypoint/manifest, and absence of
  bytecode caches and user files verified.
- 607 tests passed; Ruff lint and formatting passed.
- Manual first-use check passed.
- A fresh real-Anki smoke run did not complete in the restricted environment;
  it is not recorded as passing. Its expected menu now includes migration.
- Windows/macOS verification remains pending.

## Anki 25.07 checks — 2026-10-26

Linux, Anki 25.07, Python 3.13.17, Qt offscreen, disposable collections:

- `scripts/smoke_generation.py`: passed generation, duplicate prevention,
  selective writing cards, scheduling and review-history preservation.
- `scripts/smoke_migration.py`: passed conversion, backup, Undo, rollback,
  sibling preservation, Parts and Qt checks.
- `scripts/smoke_statistics.py`: passed the native dashboard and read-only checks.
- `scripts/smoke_settings.py`: passed saved settings and category generation.
- The packaged `scripts/anki_dev.py --smoke` check did not complete. Startup
  and menu registration succeeded, but the full UI flow remains unverified.
  Follow-up runs encountered Anki's single-instance handling.

Use 25.07 as a compatibility test candidate; these checks do not establish a
complete supported-version range or Windows/macOS compatibility.

Rebuild the archive with:

```sh
uv run --locked python scripts/build_addon.py --offline
```

## Before publishing

1. Ensure the source, documentation, issue tracker, and license links are publicly
   accessible and include these release changes.
2. Install this exact archive in an isolated profile and confirm startup, setup,
   generation, and restart. Test migration with disposable data if offering it
   in the listing. Keep a backup before testing with a real collection.
3. Review the description, screenshots, and captions. Find the screenshots in
   `docs/images/`; the listing uses eight of them. Open
   `dist/ankiweb-listing-preview.html` for a local preview. Check the layout
   on AnkiWeb before submitting.
   Publish the image files at the referenced GitHub URLs before uploading the
   description, or replace those URLs with your chosen public image host.
4. Review the compatibility fields and description, then submit the upload.
5. Record the assigned AnkiWeb ID and listing URL here, and test an installation
   using that ID in a fresh profile. Avoid keeping both the local `katanki`
   installation and the AnkiWeb installation enabled in the same profile.

AnkiWeb upload is pending.

## After publication

Record the AnkiWeb ID in the manifest's conflict list for the standalone
`katanki` package when appropriate, so installs from different distribution
channels cannot load two copies. Verify the behavior in both installation
orders before shipping that change. Keep the numeric AnkiWeb ID stable for
future updates.

Official packaging guidance: https://docs.ankiweb.net/addons/sharing
