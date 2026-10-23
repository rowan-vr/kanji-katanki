# Kanji Katanki roadmap

Progress tracker based on [the implementation specification](SPECIFICATION.md).
The specification defines requirements; this file tracks delivery and verification.

Last reviewed: **2026-10-23**. Current milestone: **Phase 3 — settings foundation**.
Phase 1 ownership-count integration is delivered. Production uses kanji meanings
and blanked examples copied from selected source vocabulary. Minimum
supported versions remain an open decision; the verified local baseline is Linux
Anki 26.09.3 / Python 3.14.8. Bundled KANJIDIC2/KanjiVG defaults are now
downloaded/prepared at build time and verified offline in the installed add-on.
Dataset payloads and upstream notice copies are ignored by Git; only source locks,
manifests, catalogs, code, and our notices are tracked. Settings can install
independent compatible data updates while retaining bundled offline defaults.

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
**Katanki → Analyze Collection**.

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
- [x] Preview scanned-note totals, distinct/existing/missing kanji, missing data,
  and a sample stroke SVG. Connect existing-note counts to Phase 2 identities.
  Implemented: scanned-note/candidate/supported/unmatched counts, dictionary details,
  missing strokes, components, SVG preview, and source attribution/fingerprints.
  Phase 2 integration: existing/missing counts now cover dictionary-supported
  kanji recognition notes, deduplicated by character. Production is independent.
  Counts remain **not assessed** when dictionaries or valid ownership data are absent.
  Evidence: `anki/analysis.py`, `scripts/smoke_generation.py`.
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
The ownership counts deferred to Phase 2 are now implemented and host-verified.
Runtime dataset download/update UI, persistent caches, and provider switching remain
later-phase work. Bundling and a maintainer-only refresh tool were pulled forward
at the user's request, with documented redistribution terms and offline tests. See [verification details](DATASETS.md#verification-recorded-on-2026-10-22).

## Phase 2 — Primitives and safe card generation

Deliverable: generate cards from selected vocabulary sources, with a preview and
explicit approval of independent, idempotent generation. Covers FR-02, FR-03, and
initial FR-04. Saved source configuration and the streamlined refresh workflow
follow in Phase 3, after generation and card content work end to end.

- [x] Define normalized stable identities and detect existing owned notes by
  character/component key within its Katanki note type in the collection.
  Evidence: `generation/planner.py`, `anki/identities.py`, and their unit tests.
  Deduplication uses the NFC character/component key and registered note type.
  No synthetic identity field or configuration scope is stored. Detection
  reports duplicate IDs and fails closed on damaged owned metadata. Real-host
  materialization and discovery-count integration pass `scripts/smoke_generation.py`.
- [x] Extract graphical components with deterministic deduplication, including
  primitives without Unicode characters.
  Evidence: `dictionaries/adapters/kanjivg_svg.py`, `tests/test_generation.py`.
  Nested/split groups are normalized; unnamed groups use source-qualified group
  keys or path fingerprints. These are provider component keys, not note IDs.
- [x] Detect graph cycles/missing nodes and produce stable prerequisite ordering.
  Evidence: `generation/planner.py`, `tests/test_planner.py`; explicit graph inputs,
  deterministic deduplication, missing-node/cycle/conflicting-definition rejection.
  Dictionary-to-graph extraction is connected through `generation/preview.py`.
- [x] Distinguish components, radicals, whole kanji, and mnemonic names; allow
  primitive prerequisites to be enabled/disabled.
  The UI labels graphical components separately and accepts explicit mnemonic
  names; unnamed/unencoded components without a supplied name are unavailable.
  No dictionary-radical or curated mnemonic system is inferred from KanjiVG.
- [x] Create separate kanji/primitive recognition and production note types, each
  with one card template and independent native Anki scheduling. Production is
  opt-in per character/primitive; recognition never generates production implicitly.
  Evidence: `generation/cards.py`, `ui/generation.py`, packaged host smoke.
- [x] Resolve production fronts and ambiguity controls.
  User decision: kanji meaning plus all distinct matching words from selected
  vocabulary fields, with every occurrence of the target replaced by `__`.
  Production is a checkbox; manual prompts are removed. Missing meanings/examples
  are unavailable. Identical clues are blocked within a plan and against existing
  same-type notes (case/whitespace normalized). Primitive production uses an
  explicitly supplied mnemonic name. Examples are immutable note content, not
  vocabulary lifecycle links. Evidence: `tests/test_generation.py` and real host.
- [x] Build a side-effect-free planner reporting create/skip/unavailable outcomes.
  Evidence: `generation/planner.py`, `tests/test_planner.py`; existing identities
  skip without updates, unavailable prerequisites propagate, and primitive
  prerequisites can be disabled. `generation/preview.py` connects normalized
  dictionary data, per-mode choices, source-word examples and mnemonic names.
- [x] Generate from the vocabulary sources selected for the current run. Reuse
  source selection from discovery; configuring and saving sources in the add-on
  settings belongs to Phase 3.
- [x] Fetch example words from the selected vocabulary list and include every
  matching entry on the kanji card front, masking each occurrence of the asked
  kanji with `_`. Show the kanji's meaning on the front as well. For `時`,
  `時間` appears as `_間`; for `間`, entries `時間` and `間` appear as
  `時_` and `_`. Include all matching vocabulary cards, including single-kanji
  entries; `真ん中` contributes to `真` and `中`, since it does not contain `間`.
  Examples come from the vocabulary list, rather than a separate dictionary
  example list.
- [x] Show the detailed plan and require explicit approval before writes.
  Evidence: packaged Qt smoke drives Cancel (no writes), then approval; previews
  list outcomes, modes, prompts, names, meanings/readings, components and strokes.
- [x] Apply approved plans through Anki APIs with error handling and idempotency.
  Evidence: `anki/generation.py`; stale previews recheck ownership, writes are
  grouped into Anki Undo, partial failures report created counts and safely resume.
  Injected partial-failure/retry and grouped Undo pass the host lifecycle harness.
  Large-batch regression: `scripts/smoke_generation_batch.py` reproduces the
  reported Undo-target eviction before the fix, then verifies 1,300 notes, single
  Undo, idempotency, and recovery after 400 successful writes. Every write is
  merged immediately so the bounded Anki Undo history retains the batch marker.
- [x] Preserve existing note/card IDs, scheduling, review history, and user edits
  unless updates are explicitly opted into.
- [x] Show offline stroke SVGs, stroke numbers, playback, and relevant components
  on card backs; handle missing SVGs gracefully.
  Evidence: real Anki webview executes stroke numbering/toggle and animation;
  cards embed sanitized SVGs and dataset attribution with no review-time downloads.
- [x] Pass the critical lifecycle test: add `景色`, generate `景` and `色`, delete
  `景色`, rescan; generated notes, progress, and due dates stay untouched, with
  no duplicates.

Verification, 2026-10-22: 75 unit tests pass; lint and formatting pass.
`scripts/smoke_generation.py` passes with Linux Anki 26.09.3 / Python 3.14.8:
actual native review history, note/card IDs, due/scheduling state and user edits
match exact snapshots after source deletion and repeated/stale approved plans.
The packaged Qt-offscreen smoke passes preview Cancel/approval, all four note
types, and stroke controls executed in the real Anki webview. Human visual review
and Windows/macOS verification remain pending. Persistent source configuration
in add-on settings is the next requested step; session source selection is retained.

Local acceptance: selected sources produce the expected cards, with vocabulary-derived
masked examples and the kanji meaning on the front. Approved generation is safe
to rerun and remains independent of source vocabulary. No source lifecycle
tracking or direct collection-database writes.

## Phase 3 — UX, saved settings, and refresh

Deliverable: once Phase 2 generation works, make everyday use a single refresh
using the user's saved configuration.

- [x] Configure vocabulary sources (decks, note types, and fields) in the add-on
  settings and persist them across Anki restarts.
  Discovery settings support multiple deck/pattern → note type → field rules.
  `*` covers all decks; matching decks include subdecks. Overlapping rules union
  selected fields and count each note once. Explicit deck choices retain IDs.
  Evidence: `config/__init__.py`, `ui/settings.py`, `tests/test_settings.py`, and
  `scripts/smoke_settings.py` (real collection close/reopen, 2026-10-23).
  Refresh and Settings are under the top-level **Katanki** menu.
  The source editor uses compact labeled rows and a checkbox popup for fields;
  multi-field summaries keep longer note types from making the editor taller.
  **Test discovery** scans unsaved source rows in the background and shows note,
  vocabulary, and kanji candidate counts and lists without saving or generating.
  Real-host smoke verifies exact settings and notes/cards/revlog preservation.
- [x] Save generation preferences and provide recommended defaults with versioned
  configuration and safe migrations.
  Recognition, Production, and Parts subtabs save category selection, target decks,
  default tags, and all/filtered source-tag copying. Enabled categories are selected
  during refresh; the single creation review gates new cards. Recognition and Production default on.
  Part tags inherit source vocabulary tags through the component graph. Decks/tags
  are snapshotted in the preview and applied only to new notes. Missing settings use safe defaults;
  malformed/future versions fail without overwriting data. Version 1/2 settings
  migrate to version 5 while preserving source IDs and deck/component preferences.
  Preview approval remains required; background triggers and update approvals belong
  to the remaining refresh work.
  Dictionaries settings select bundled/local/disabled KANJIDIC2 and KanjiVG sources;
  background checks expose detected provenance, errors, and a sample stroke check.
  Attribution includes source/license links, bundled versions/counts/checksums, and
  packaged notice copies. Real-host smoke covers Save/reopen, checks without writes,
  and disabled sources respected by discovery.
- [x] Provide one refresh button that loads the configured sources and preferences,
  scans vocabulary, plans generation, and applies the configured workflow.
  **Katanki → Refresh and generate Kanji Cards** replaces Analyze Collection.
  Saved sources/dictionaries are scanned in the background; enabled generation
  categories and deck/tag preferences populate one creation review. Refresh itself
  requires no approval; existing cards are skipped. Only eligible new cards are
  shown as green tiles under Recognition/Production/Parts tabs. Disabled categories
  are excluded. Left-click renders a front/back preview inline; right-click saves
  a per-card-type ignore immediately, including on Cancel. Settings → Ignored cards
  restores eligibility for future refreshes. Missing decks can be chosen in this
  same review. Explicit approval gates creation; refresh never deletes notes.
  The old `ui/discovery.py` and old generation/verification windows are deleted.
  Evidence: `ui/refresh.py`, `tests/test_refresh.py`, `scripts/smoke_refresh.py`.
  Real-host verification covers Cancel with exact data preservation, approval,
  category decks/tags, duplicate clicks, tile state/preview, persistent ignore/restore,
  and quiet no-op refreshes without a review window. Parts-only tabs and choosing
  missing target decks in the same review are host-verified.
- [x] Add Cards settings between Generation and Dictionaries with Recognition,
  Production, and Parts subtabs. Version 5 persists independent front-example,
  discovered/default-word, furigana, automatic-example-refresh (default on), and
  seen/new vocabulary choices for Recognition and Production. Parts has front-name,
  back example-kanji, vocabulary-only/other-kanji, and automatic-refresh controls;
  it has no furigana or word review-status controls. Versions 1–4 migrate without modifying saved data
  or losing existing preferences. Evidence: `tests/test_card_settings.py`;
  `scripts/smoke_settings.py` covers tab order, independent Save/Cancel and reopening.
  Verification, 2026-10-23: 189 unit tests, lint/formatting, real-collection
  persistence, and the packaged Qt-offscreen Anki smoke pass.
  This delivers the settings UI and persistence; applying display choices to card
  content and refreshing examples remain part of the unchecked work below.
  Jitendex default-word packs and dictionary-backed readings are deferred to a
  separate PR; export mapping and ranking still need investigation.
- [ ] Implement the [card example design](CARD_EXAMPLES.md): managed
  `VocabExamples` and protected `UserExamples`, all eligible examples stored,
  per-category display limit (default 5; 0 = all), user examples first, stable
  deduplication, production masking, and ambiguity checks on the visible clues.
  Parts uses example kanji on the back. The limit control is saved per category;
  rendering, fields, and refresh integration are pending.
- [ ] Add automatic refresh with configurable triggers and clear enabled/disabled
  controls, reusing the same saved configuration and generation safeguards.
- [ ] Define how refresh updates vocabulary examples on existing cards while
  preserving user edits, note/card identities, scheduling, and review history;
  require explicit opt-in for updates as established in Phase 2.
- [ ] Show progress, results, and actionable errors; make empty or invalid source
  settings easy to correct.
- [ ] Verify saved settings survive restarts, repeated refreshes create no
  duplicates, and manual/automatic refresh preserve existing review progress.

Verification, 2026-10-23: 131 unit tests pass; lint and formatting pass.
`scripts/smoke_settings.py` confirms persistence after closing/reopening a real
Anki collection, mixed note types/fields, and overlapping wildcard deduplication. Category generation checks verify separate
recognition/production/parts decks, default/filtered/inherited tags, missing-deck
rejection before writes, and idempotent reruns.
The packaged Qt-offscreen smoke passes top-level menu registration,
tabbed Settings Save/Cancel and reopening, Add/Remove source rows, saved
discovery/generation defaults, exact
notes/cards/revlog preservation during settings/scans, generation Cancel/approval,
and stroke controls on Linux Anki 26.09.3 / Python 3.14.8. Human visual review is pending.

Acceptance: after configuring sources and preferences once, pressing refresh runs
all configured steps without repeating setup. Automatic refresh uses the same
workflow and respects the user's update choices.

## Phase 4 — Statistics and modern interface

Deliverable: a dashboard driven by actual Anki progress. Covers FR-05 and the
detail-view portion of FR-04.

- [ ] Normalize Anki review snapshots without adding a separate scheduler.
- [ ] Aggregate unique kanji/primitive states: unseen, learning, young, mature,
  and relearning; include retention and progress history.
- [ ] Separate recognition and writing evidence; distinguish missing production
  notes from failed writing cards.
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

## Phase 5 — Public beta

Deliverable: a documented, self-contained release for ordinary desktop Anki users.
Covers FR-06 and production readiness of the dictionary subsystem.

- [ ] Verify the saved settings, defaults, and configuration migrations delivered
  in Phase 3 are ready for public release.
- [ ] Decide dataset bootstrap strategy and provide setup/install/update/status UI.
  Decision resolved: bundle essential KANJIDIC2/KanjiVG data for offline first use.
  Optional local overrides, license UI, runtime update checks/downloads, result
  popups, and return-to-bundled controls exist. Public-release verification remains.
- [ ] Implement generic HTTPS downloads, checksum/version validation, safe archive
  extraction, decompression limits, and atomic cache replacement.
  Implemented for the existing dictionary packs; verify the complete production
  publishing and update path before public release.
- [ ] Improve the maintainer workflow for independent dataset releases.
  Current baseline: the monthly/manual [Dataset packs workflow](../.github/workflows/datasets.yml)
  prepares validated candidates; manual runs can publish assets. Catalog promotion
  and updating the bundled baseline still require manual coordination. See
  [dataset maintenance](DATASETS.md#maintainer-preparation-and-regular-updates).
  - [ ] Detect upstream changes, including new KanjiVG releases, and skip unchanged
    packs. Produce a review summary of versions, entry/coverage changes, parser
    warnings, download sizes, checksums, and license/provenance differences.
  - [ ] Allow a maintainer to approve and publish an existing candidate artifact
    without downloading upstream again or regenerating the reviewed bytes.
    Publish immutable assets first, then verify their public download URLs, sizes,
    hashes, pack metadata, and included notices before any catalog promotion.
  - [ ] Open a promotion PR with the exact published catalog. Distinguish runtime
    dictionary updates from a new bundled baseline; baseline changes also update
    the build lock, manifests, and source provenance together. Prevent stale tags,
    missing release assets, and mismatched hashes from reaching the default branch.
  - [ ] Gate promotion on clean-cache builds on Linux, macOS, and Windows, including
    CRLF checkout coverage, plus runtime install/update and bundled-fallback checks.
    Keep live-upstream failures confined to dataset maintenance, outside normal CI.
  - [ ] Keep dataset and add-on release discovery separate. Support normal dataset
    releases with `--latest=false`; retain the initial `datasets-2026-10-23`
    prerelease. The catalog determines the newest compatible dictionaries.
  - [ ] Document and verify rollback to a previously published compatible catalog
    entry, preserving older packs for installed users and reproducible builds.
    Explain the distinction between withdrawing an update and downgrading users
    who already installed it. Surface failed preparation/publication runs and
    provide a retry path that never overwrites a published asset.
  Acceptance: a maintainer can review, publish, promote, and withdraw dictionary
  updates without copying metadata by hand, committing dataset payloads, releasing
  new add-on code, or breaking offline use and existing build locks.
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

## Phase 6 — Optional enhancements (post-beta)

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
  Independent updates for existing defaults now use versioned release packs and
  a small catalog, with bundled offline fallback. Additional providers and
  per-character downloads remain deferred.
- [ ] Custom primitive names and exclusions.
- [ ] Additional classifications: Jōyō, school grade, frequency, and custom packs.
- [ ] Enhanced stroke animation and optional handwriting canvas/validation.
  Automatic handwritten-stroke recognition remains outside the current scope.
- [ ] Public third-party extension API after internal interfaces stabilize.

## Decision log — unresolved

Resolved 2026-10-22 by the user: recognition and production use separate note
types so production can be selected for a smaller set of characters. Deduplicate
within each Katanki note type using the character/component field; no stored
synthetic identity or configuration scope. Core planning and detection tests cover
this policy; note type creation and per-character/component selection are now
implemented and pass the packaged host smoke.

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
- [x] Kanji production front and ambiguity policy.
  User decision: dictionary meanings plus masked matching source vocabulary,
  automatic from selected sources, with production opt-in per character.
- [ ] Primitive naming system and component/radical distinctions.
- [ ] Final packaging/resource approach for the embedded frontend.
  The Python `src/` layout already builds into a root-entrypoint archive.
