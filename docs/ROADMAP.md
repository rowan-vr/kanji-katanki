# Kanji Katanki roadmap

Progress tracker based on [the implementation specification](SPECIFICATION.md).
The specification defines requirements; this file tracks delivery and verification.

Last reviewed: **2026-10-22**. Current milestone: **Phase 1 — read-only discovery
POC delivered**, with ownership-count integration deferred to Phase 2. Minimum
supported versions remain an open decision; the verified local baseline is Linux
Anki 26.09.3 / Python 3.14.8. Bundled KANJIDIC2/KanjiVG defaults are now
downloaded/prepared at build time and verified offline in the installed add-on.
Dataset payloads and upstream notice copies are ignored by Git; only source locks,
manifests, code, and our notices are tracked. On-demand downloads are deferred.

## How to maintain this tracker

- Check an item only when its implementation and relevant verification are complete.
- Leave partially completed items unchecked; describe completed parts beneath them.
- Link tests, documentation, or a PR when checking off work. Record manual host
  checks with their date, platform, and Anki/Python versions.
- Update this file in the same change as the work. Reopen an item if a regression
  invalidates it. Keep future requirements in the specification and tracker aligned.
- A phase is complete when every required item and its acceptance check are done.
  Optional enhancements do not block earlier milestones.

Verification was rerun for the Phase 1 implementation on 2026-10-22; evidence
below distinguishes automated tests, real-host checks, and remaining decisions.

## Phase 0 — Bootstrap

Deliverable: install in an isolated Anki profile and open
**Tools → Kanji Katanki → Analyze Collection**.

- [x] Set up the uv project, pytest, ruff, and reproducible lockfile.
  Evidence: `pyproject.toml`, `uv.lock`.
- [x] Implement the add-on entrypoint and menu/status dialog.
  Evidence: `src/katanki/__init__.py`, `src/katanki/anki/integration.py`.
- [x] Add logging and graceful startup/dialog failure handling.
  Evidence: integration implementation and `tests/test_integration.py`.
- [x] Add host-boundary and packaging unit tests.
  Evidence: `tests/test_integration.py`, `tests/test_packaging.py`.
- [x] Document local build/install and provide an isolated test-profile helper.
  Evidence: [README](../README.md#development), `scripts/build_addon.py`,
  `scripts/anki_dev.py`.
- [x] Smoke-test the packaged add-on in real Anki without changing note/card counts.
  Evidence: [recorded smoke result](../README.md#compatibility), 2026-10-22,
  Linux Anki 26.09.3 / Python 3.14.8, Qt offscreen.
- [ ] Select and document minimum supported Anki/Python versions.
  One local host has been verified; this does not establish minimum versions.

Acceptance: menu and dialog verified locally; support-version decision remains open.

## Phase 1 — Read-only discovery and dictionary POC

Deliverable: select scan sources, inspect unique kanji and dictionary/stroke data,
and leave the collection unchanged. Covers FR-01 and the initial dictionary work.

- [x] Introduce only the shared models/provider protocols needed by discovery.
  Evidence: [contracts](../src/katanki/common/models.py). No parallel agent work.
- [x] Select target decks, note types, and fields through the scan UI.
  Evidence: [dialog](../src/katanki/ui/discovery.py); one note type per scan,
  multiple decks/fields, and included subdecks. Choices are session-only.
- [x] Implement pure-Python kanji extraction and character deduplication.
  Evidence: [discovery](../src/katanki/generation/discovery/__init__.py).
- [x] Add a read-only Anki collection adapter for configured sources.
  Evidence: [adapter](../src/katanki/anki/collection.py), [tests](../tests/test_discovery.py).
- [x] Distinguish dictionary-supported kanji from unmatched/unclassified candidates.
  Evidence: [classification](../src/katanki/generation/discovery/report.py).
- [x] Manually review the “no dictionary loaded” state and results shown as
  “not classified”.
  Evidence: user confirmed review on 2026-10-22; exact host/runtime versions
  were not separately reported.
- [x] Validate dataset manifests and expose normalized dictionary interfaces.
  Evidence: [registry](../src/katanki/dictionaries/registry.py),
  [manager](../src/katanki/dictionaries/manager.py), [tests](../tests/test_dictionaries.py).
  Bundled snapshots include versions, checksums, notices, and offline default selection;
  [bundle tests](../tests/test_bundled_datasets.py) cover all supported SVGs.
- [x] Load KANJIDIC2 and KanjiVG through reusable format adapters.
  Evidence: [adapters](../src/katanki/dictionaries/adapters),
  [real-upstream check](DATASETS.md#verification-recorded-on-2026-10-22).
- [ ] Preview scanned-note totals, distinct/existing/missing kanji, missing data,
  and a sample stroke SVG. Connect existing-note counts to Phase 2 identities.
  Implemented: scanned-note/candidate/supported/unmatched counts, dictionary details,
  missing strokes, components, SVG preview, and source attribution/fingerprints.
  Remaining: existing/missing owned-note counts explicitly show **not assessed**;
  these depend on the Phase 2 ownership contract and must not be guessed as zero.
- [x] Document fetching/preparing sample data without committing unreviewed datasets.
  Evidence: [dataset preparation](DATASETS.md). Reviewed KANJIDIC2 subset and
  pinned KanjiVG data are bundled at build time with their own licenses; both raw
  downloads and generated payloads/notices remain ignored by Git.
- [x] Test extraction (`景色`, `少数民族`, kana-only, punctuation, mixed scripts)
  and deduplication, including HTML/media references and supplementary ideographs.
  Evidence: [extraction and adapter tests](../tests/test_discovery.py).
- [x] Verify scans change zero notes/cards, including source fields and tags.
  Evidence: [real-host harness](../scripts/smoke_discovery.py); 2026-10-22,
  Linux Anki 26.09.3 / Python 3.14.8, Qt offscreen. Exact notes/cards/revlog
  snapshots matched across repeated scans and the packaged UI operation.

Manual check, 2026-10-22: the user confirmed the refreshed development add-on
works in their Anki installation after following the manual test instructions.
Individual test outcomes and exact host/runtime versions were not separately
reported; this supplements the versioned automated host evidence above.

Acceptance: the core POC is verified against a sample vocabulary deck, with
synthetic dictionary/stroke fixtures and a separate official-upstream parser check.
The phase's full checklist remains open only for ownership counts tied to Phase 2.
Runtime dataset download/update UI, persistent caches, and provider switching remain
later-phase work. Bundling and a maintainer-only refresh tool were pulled forward
at the user's request, with documented redistribution terms and offline tests. See [verification details](DATASETS.md#verification-recorded-on-2026-10-22).

## Phase 2 — Primitives and safe card generation

Deliverable: preview and explicitly approve independent, idempotent generation.
Covers FR-02, FR-03, and initial FR-04.

- [ ] Define normalized stable identities and detect existing owned notes by
  character/primitive, applicable note type, and collection/configuration scope.
- [ ] Extract graphical components with deterministic deduplication, including
  primitives without Unicode characters.
- [ ] Detect graph cycles/missing nodes and produce stable prerequisite ordering.
- [ ] Distinguish components, radicals, whole kanji, and mnemonic names; allow
  primitive prerequisites to be enabled/disabled.
- [ ] Create kanji/primitive templates with configurable recognition and production
  cards and independent native Anki scheduling.
- [ ] Resolve production prompt defaults and configurable ambiguity controls.
- [ ] Build a side-effect-free planner reporting create/skip/unavailable outcomes.
- [ ] Show the detailed plan and require explicit approval before writes.
- [ ] Apply approved plans through Anki APIs with error handling and idempotency.
- [ ] Preserve existing note/card IDs, scheduling, review history, and user edits
  unless updates are explicitly opted into.
- [ ] Show offline stroke SVGs, stroke numbers, playback, and relevant components
  on card backs; handle missing SVGs gracefully.
- [ ] Pass the critical lifecycle test: add `景色`, generate `景` and `色`, delete
  `景色`, rescan; generated notes, progress, and due dates stay untouched, with
  no duplicates.

Acceptance: approved generation is safe to rerun and remains independent of source
vocabulary. No source lifecycle tracking or direct collection-database writes.

## Phase 3 — Statistics and modern interface

Deliverable: a dashboard driven by actual Anki progress. Covers FR-05 and the
detail-view portion of FR-04.

- [ ] Normalize Anki review snapshots without adding a separate scheduler.
- [ ] Aggregate unique kanji/primitive states: unseen, learning, young, mature,
  and relearning; include retention and progress history.
- [ ] Separate recognition and writing evidence; distinguish missing writing
  templates from failed writing cards.
- [ ] Select and validate an unofficial JLPT source; expose provenance/version and
  define coverage for omitted characters.
- [ ] Implement classification registry, N5–N1 coverage graphs, and mode toggle.
- [ ] Build searchable kanji grid/explorer and per-character detail pane with
  stroke links and offline stroke display/playback.
- [ ] Bundle React/TypeScript static assets in an Anki webview with an explicit
  bridge; require no local web server.
- [ ] Test unique-identity counts, duplicate suppression, mixed progress, missing
  writing cards, and classification gaps.

Acceptance: dashboard counts match Anki evidence and never imply writing mastery
from recognition alone.

## Phase 4 — Public beta

Deliverable: a documented, self-contained release for ordinary desktop Anki users.
Covers FR-06 and production readiness of the dictionary subsystem.

- [ ] Provide recommended defaults, scan settings, and versioned configuration
  with safe migrations.
- [ ] Decide dataset bootstrap strategy and provide setup/install/update/status UI.
  Decision resolved: bundle essential KANJIDIC2/KanjiVG data for offline first use.
  Optional local overrides and license UI exist; runtime install/update/status UI is pending.
- [ ] Implement generic HTTPS downloads, checksum/version validation, safe archive
  extraction, decompression limits, and atomic cache replacement.
- [ ] Preserve the last working dataset after failed or interrupted imports.
- [ ] Verify installed dictionary lookups and review flows work offline.
  Bundled dictionary lookups and SVG previews pass offline unit/packaged-host checks.
  Generated review flows do not exist yet and remain unverified.
- [ ] Handle missing/malformed datasets, version mismatch, and interrupted operations.
- [ ] Test performance on realistically large collections.
- [ ] Smoke-test installation and supported host versions on Windows, macOS, Linux.
- [ ] Review upstream licenses, field restrictions, redistribution, and attribution
  before bundling or publishing third-party data.
  Completed for the current KANJIDIC2 subset and KanjiVG bundle: separate CC licenses,
  copied upstream terms/docs, retained SVG notices, modification disclosure, and
  maintainer update procedure. See [notices](../THIRD_PARTY_NOTICES.md).
  Future datasets/fields and later card exports still require their own review.
- [ ] Finish user documentation, screenshots, changelog, and backup guidance.
- [ ] Automate `.ankiaddon` releases and publish through AnkiWeb/GitHub.
  The archive builder and GitHub-release asset workflow exist; end-to-end release
  verification and AnkiWeb publication remain pending.
- [ ] Verify unrelated notes remain untouched and generation preserves progress.

Acceptance: users can install and use the release without Python, uv, Node.js,
accounts, telemetry, or network-required reviews.

## Phase 5 — Optional enhancements (post-beta)

- [ ] FR-07: explicit Migaku Kanji GOD import with backup, dry-run mappings,
  unmappable-data warnings, confirmation, and copied-profile tests; preserve
  scheduling/history only where a safe mapping is proven.
- [ ] Manual kanji entry and imported lists.
- [ ] JMdict integration and optional vocabulary-writing cards using reading plus
  meaning/context, with homophone ambiguity controls.
- [ ] Additional dictionary providers, capability/fallback selection, and supported
  provider switching without silently rewriting cards.
- [ ] On-demand dataset packs and/or per-character stroke downloads.
  Deferred at the user's request, 2026-10-22. Evaluate source granularity (whole
  dictionary archives versus individual SVGs or prepared packs), explicit download
  controls, version/checksum/license tracking, bounded local caching, cancellation,
  retry, and prefetch. Reuse cached data offline and keep review flows usable without
  network access; report missing data instead of fetching during every review.
  Current delivery remains a build-time download plus a self-contained bundle.
- [ ] Custom primitive names and exclusions.
- [ ] Additional classifications: Jōyō, school grade, frequency, and custom packs.
- [ ] Enhanced stroke animation and optional handwriting canvas/validation.
  Automatic handwritten-stroke recognition remains outside the current scope.
- [ ] Public third-party extension API after internal interfaces stabilize.

## Decision log — unresolved

Record decisions and supporting evidence here when resolved; do not silently pick
defaults for the specification's open questions.

- [ ] Minimum supported Anki desktop versions and matching Python runtime.
- [ ] Third-party dataset licensing and redistribution obligations.
- [x] Bundled essential data versus first-run downloads.
  User decision, 2026-10-22: download/prepare defaults during builds, keep payloads
  out of Git, and ship KANJIDIC2 subset + KanjiVG inside the add-on; no network
  required at first use. Explicit local overrides remain available. Versions,
  checksums, redistribution terms and refresh procedure: [datasets](DATASETS.md).
- [ ] Unofficial JLPT source, validation, and coverage semantics.
- [ ] Default kanji production prompt and ambiguity policy.
- [ ] Primitive naming system and component/radical distinctions.
- [ ] Final packaging/resource approach for the embedded frontend.
  The Python `src/` layout already builds into a root-entrypoint archive.
