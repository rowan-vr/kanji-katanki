# Kanji Katanki roadmap

Progress tracker based on [the implementation specification](SPECIFICATION.md).
The specification defines requirements; this file tracks delivery and verification.

Last known: **2026-10-26**. Phases 3 and 4 are complete. Current milestone:
**Phase 5 — public beta**. Existing-card migration and restartable first-run
setup are delivered; cross-platform and end-to-end release verification remain.
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
- [x] Document fetching/preparing sample data without committing unknown datasets.
  Evidence: [dataset preparation](DATASETS.md). Known KANJIDIC2 subset and
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
  Dictionaries settings select bundled/local/disabled KANJIDIC2, KanjiVG and Jitendex sources;
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
  content is partially delivered below, including existing-note refresh. Remaining
  display work, furigana alignment, and seen/new filtering move to Phase 4 with
  the interface improvements.
- [x] Bundle a pinned Jitendex-derived offline word pack and suggest examples during creation.
  `scripts/bundle_datasets.py` verifies source checksums and packages licenses;
  normal add-on builds retain the complete 38.8 MB export plus a lightweight index
  of 17,126 common word forms. The full add-on stays below 50 MB; filtering applies
  only to suggestions. Defaults are opt-in through
  the existing discovered/default setting and follow deduplicated source vocabulary.
  Recognition backs and production clues use the suggestions; Parts backs use
  containing kanji from the scan. All managed suggestions are stored separately,
  limits apply at display/clue generation, and ambiguity checks use visible clues.
  Exact previous stock templates can be upgraded under Undo; custom templates remain
  untouched. Evidence: `tests/test_word_suggestions.py`, packaging/offline checks,
  `scripts/smoke_word_examples.py`. Verification, 2026-10-23: 196 unit tests,
  lint/formatting, offline add-on build, real Anki migration/Undo and packaged
  Qt rendering checks pass (Linux Anki 26.09.3 / Python 3.14.8).
- [x] Add **Katanki → New Kanji Cards** with a text box for manual kanji entry.
  Unique characters use the same dictionary classification, configured generation,
  parts, decks/tags, ignores, duplicate checks, and creation review as discovery;
  no vocabulary sources are required. Evidence: `tests/test_manual.py`.

- [x] Integrate Jitendex into the shared dictionary list and independent update sequence.
  Bundled/installed/local Yomitan ZIP/disabled selection drives generation and
  example Refresh. Settings exposes validation, versions, fingerprints, original
  attribution, license notices and bundled fallback. Maintainer preparation and the
  monthly/manual workflow produce three verified packs and a candidate catalog;
  Jitendex same-day build revisions sort correctly. All payloads now live under
  `bundled/` and normal builds restore all three packs from the same build lock.
  Source preparation uses the shared `bundled/SOURCES.json`; there is no separate
  word-pack build path. The combined baseline is published under
  `datasets-2026-10-23-jitendex`; merging the catalog advertises it to clients. Older
  published releases remain available for earlier commits. Evidence: `tests/test_jitendex_dictionary.py`,
  `tests/test_dataset_pack_builds.py`, and `scripts/smoke_settings.py`.
  Verification, 2026-10-23: 251 tests, lint/formatting, offline add-on/candidate-pack
  builds and real Anki/Qt selection/update/fallback checks pass. Published assets
  were downloaded and hash-checked against the shared build lock.
- [x] Add automatic refresh with configurable triggers and clear enabled/disabled
  controls, reusing the same saved configuration and generation safeguards.
  Settings → Refresh has a master switch (default off), profile-open and sync-finish
  triggers. Version 6 migrates versions 1–5 with automation disabled. Triggers
  coalesce and wait for the deck list, modal dialogs, progress operations, and
  active refreshes; profile closure discards pending work. Automatic scans use
  the existing creation review; managed example updates now follow the update
  preferences and edit-protection rules below. Results arriving
  during review are deferred; disabling automation cancels a pending run.
  Evidence: `anki/automatic_refresh.py`, `tests/test_automatic_refresh.py`,
  `tests/test_refresh.py`, and Save/Cancel/reopen checks in `scripts/smoke_settings.py`.
  Verification, 2026-10-23: 213 unit tests and lint/formatting pass; real-Anki
  collection persistence (including nondefault refresh choices) and idempotent
  category generation pass. The packaged Qt-offscreen smoke was attempted but
  timed out in `QApplication.__init__`, before add-on loading; the new Refresh
  UI Save/Cancel/reopen assertions were added. Subsequent human acceptance confirms
  automatic refresh and visual behavior pass (2026-10-23). Cross-platform release
  verification remains in Phase 5; this acceptance does not claim Windows/macOS coverage.
- [x] Define how refresh updates vocabulary examples on existing cards while
  preserving user edits, note/card identities, scheduling, and review history;
  require explicit opt-in for updates as established in Phase 2.
  Refresh settings now save **Update tags from source vocabulary** (default off)
  **Update example words** (default on), and **Update dictionary data** (default off),
  independently of automatic triggers. Dictionary updates here mean existing-card
  content from selected dictionaries, rather than downloading dictionary packs.
  Existing version 6 settings receive these defaults without changing other choices.
  Example updates now apply through Anki CollectionOp and grouped Undo, independently
  of new-card creation. Both refresh gates are respected. Generated-value baselines
  protect manual edits; legacy notes require explicit before/after migration review.
  Automatic refresh skips unapproved migrations. UserExamples, IDs, scheduling,
  history and decks are preserved; existing tags are retained when adding source tags.
  Source removal clears recognition/Parts
  examples without deleting notes; empty/ambiguous production updates are withheld.
  Stale notes, source scans, settings and new clue collisions are rechecked before
  writes. Source-tag updates add configured tags without removing existing tags and
  reject stale tag snapshots. Dictionary-content updates refresh meanings, readings,
  components, strokes and attribution independently of example updates; unavailable
  stroke data does not erase an existing diagram. Combined updates retain a valid
  generated-value baseline. Delivered in `a6a0461`; regression coverage in
  `tests/test_example_refresh.py` checks independent update choices, retained user
  examples/tags, stale-tag rejection and idempotent reruns. Save/Cancel/reopen
  assertions cover the settings in `scripts/smoke_settings.py`.
  Verification, 2026-10-23: 238 unit tests, lint/format checks, offline build,
  `scripts/smoke_example_refresh.py` (real Anki updates/Undo), and the packaged Qt
  Refresh-button update/rendering smoke pass on Linux Anki 26.09.3 / Python 3.14.8.
- [x] Show progress, results, and actionable errors; make empty or invalid source
  settings easy to correct.
  Refresh runs with background progress and reports updates, ready/existing cards,
  unavailable cards and no-op results. Empty, unmatched or invalid sources open
  persistent feedback with **Edit sources…**; saving corrected settings retries
  Refresh. Dictionary failures identify the settings to check. Automatic runs
  report source issues without opening a source editor. Manual creation reports
  lookup progress and actionable results. Persistent Jitendex indexes avoid repeated
  full-dictionary conversion; progress describes cache loading/indexing.
  Delivered in `050da6b`, with Windows UTF-8 cache handling corrected in `6fa5bf5`.
  Evidence: `ui/refresh.py`, `ui/refresh_feedback.py`, `ui/manual.py`,
  `tests/test_refresh.py`, `tests/test_manual.py`, `tests/test_suggestion_cache.py`,
  and `tests/test_jitendex_dictionary.py`. Human visual acceptance passed,
  reported 2026-10-23.
- [x] Verify saved settings survive restarts.
  Human acceptance check passed, reported 2026-10-23.
- [x] Improve the refresh replacement/migration review dialog and repeat visual
  acceptance. Human review failed, reported 2026-10-23: the dialog presents a dense
  text dump with raw example HTML, internal field names and note IDs, making
  before/after replacements difficult to compare. Present readable card/field
  changes with clear before/after grouping while retaining explicit approval.
  Replacement UI implemented on `fix/refresh-replacement-dialog`: selectable card
  list, side-by-side current/proposed values, readable example text and field labels,
  and note IDs in tooltips. Qt-offscreen checks pass card selection, readable values,
  Cancel and approval. Human visual acceptance passed, reported 2026-10-23.
- [x] Verify repeated refreshes create no duplicates and manual/automatic refresh
  preserve existing note/card identities, scheduling and review history.
  Human acceptance checks passed, reported 2026-10-23.
- [x] Verify automatic refresh and complete human visual acceptance.
  Both checks passed, reported 2026-10-23. Phase 3 acceptance is complete.

Verification, 2026-10-23: 131 unit tests pass; lint and formatting pass.
`scripts/smoke_settings.py` confirms persistence after closing/reopening a real
Anki collection, mixed note types/fields, and overlapping wildcard deduplication. Category generation checks verify separate
recognition/production/parts decks, default/filtered/inherited tags, missing-deck
rejection before writes, and idempotent reruns.
The packaged Qt-offscreen smoke passes top-level menu registration,
tabbed Settings Save/Cancel and reopening, Add/Remove source rows, saved
discovery/generation defaults, exact
notes/cards/revlog preservation during settings/scans, generation Cancel/approval,
and stroke controls on Linux Anki 26.09.3 / Python 3.14.8. Human acceptance has
confirmed restart persistence, duplicate-free repeated refreshes, preservation of
existing note/card identities and review progress, automatic refresh, and visual
behavior including the revised replacement/migration dialog (2026-10-23).

Acceptance: after configuring sources and preferences once, pressing refresh runs
all configured steps without repeating setup. Automatic refresh uses the same
workflow and respects the user's update choices.

## Phase 4 — Statistics and modern interface

Deliverable: polished, portable review cards and a dashboard driven by actual
Anki progress. Covers FR-03, FR-05 and the detail-view portion of FR-04.

Completed 2026-10-26: portable card layouts, reusable target datasets, the native Qt
statistics dashboard, list-based creation, and historical progress/retention charts. See the [target-list and statistics plan](KANJI_STATS.md)
for the canonical format, source provenance, dashboard and Anki progress policy.
Personal-list management and persisted group selection are also delivered.
Statistics cover kanji recognition/writing; a separate Parts/primitive dashboard
is outside the completed scope.

- [x] Implement the versioned target-list contract, validation, registry, and
  ordered unique group selection independently of Anki and dictionary coverage.
  Evidence: `stats/targets.py`, shared `common/characters.py`, and
  `tests/test_target_lists.py`. Built-ins reuse dataset manifests, pack validation,
  updates, locked builds and offline fallback through `target_lists_json`;
  `tests/test_target_datasets.py` covers multiple providers, failed installs,
  overrides, checksum fallback and offline pack restore.
- [x] Bundle pinned, attributed school-grade/Jōyō datasets and list/group selection.
  Separate `school-grades` (1,026 elementary targets, grades 1–6) and `joyo`
  (all 2,136 Jōyō targets) entries are delivered, each with its own
  manifest/version/pack and generated canonical JSON.
  `scripts/generate_target_lists.py` derives it from pinned KANJIDIC2 data; runtime
  dictionary changes do not affect it. Clean builds restore checksum-pinned list
  bytes. Both list ZIPs are published in `datasets-target-lists-2026-10-25`;
  catalog/build-lock entries use verified public URLs. Shared cold-list-cache and
  offline restore pass. List/group selection is available in the dashboard.
  Source controls now live in **Settings → Statistics → Lists**, separately from
  Dictionaries, using the same canonical format and dataset lifecycle. Real
  Anki/Qt verification: `scripts/smoke_statistics_settings.py` (2026-10-25) covers
  page separation, source persistence/cancel, update filtering and shared schedule.
  Modern unofficial JLPT is delivered below; additional exam/textbook adapters
  remain future sources.
- [x] Add personal-list import/export and profile-specific list storage/management.
  **Settings → Statistics → Personal lists** supports canonical JSON import review,
  provenance/group counts, validation warnings, explicit replacement with member
  diffs, export and confirmed removal. Files are profile-local under `user_files`
  and do not sync; export/import transfers them. Personal lists join the dashboard
  registry and version 8 settings retain list/group selection. File changes apply
  immediately after confirmation, independently of Settings Save/Cancel.
  Evidence: `tests/test_personal_target_lists.py`, dashboard/Qt tests,
  real-Anki `scripts/smoke_personal_target_lists.py` (including unchanged
  notes/cards/revlog), and an offline add-on package build (2026-10-25).

- [x] **Polish card layouts.** Improve recognition, production, and Parts review
  layouts for desktop and mobile, including readable typography, spacing,
  responsive examples, and usable stroke controls. Cards must remain fully
  studyable offline without the add-on, including after export/import and on
  portable review clients. Package required templates, styles, scripts, and media
  with the notes/deck; review must not depend on an add-on bridge, local server,
  installed dictionaries, or source vocabulary decks. The add-on is for easy
  creation and refresh, not a requirement for studying existing cards.
  Include the remaining [card example design](CARD_EXAMPLES.md): seen/new
  vocabulary filtering, remaining display controls, and preview parity. Editable
  user examples and live clues after editor changes are deferred to Phase 6.
  Preserve the delivered managed/protected fields, all-example storage,
  per-category front limits (default 5; 0 = all), stable deduplication,
  production masking and visible-clue ambiguity checks, Parts back examples, and
  protected existing-note refresh. Complete the remaining example acceptance
  coverage as part of this work. Resolve source-dependent filtering at creation
  or refresh and store the data needed for independent review on the notes.
  Verify front/back rendering, examples, masking, furigana, and stroke controls
  on desktop and responsive mobile-sized webviews, plus an exported deck imported into a clean profile
  without the add-on or source decks, offline.
  Implemented 2026-10-24: distinct front/back layouts without instruction prompts
  or repeated front content, responsive type/spacing, inline strokes, touch-sized
  controls, and night mode (`generation/card_layout.py`). Backs show all configured
  words sorted known → relearning → learning → new → no card, with distinct blue,
  rose double-border, amber dashed-border, plain-outline, and gray chips. Long lists
  show 12 chips with an expandable remainder and a full word count; creation and
  refresh preserve the entire configured list independently of front limits.
  Statuses are portable snapshots updated
  at creation/refresh. Exact old stock layouts upgrade during creation/refresh;
  custom templates/styles are preserved. `scripts/smoke_card_layout.py` verifies
  clean export/import without source vocabulary, standalone offline rendering,
  word states/order/styles, expansion of all 16 test words despite a front limit
  of one, masking and stroke controls at 360/900 px in light/dark themes.
  Change-tracking records now escape embedded HTML to survive the Anki editor;
  recognized old attribute-quote damage is recovered automatically and compared
  against current fields before updates. Manual edits remain protected; unknown
  damage still uses replacement review. Qt reproduces the old corruption and
  verifies recovery; real-Anki checks cover first review, automatic/approved repair,
  preservation, idempotency, and Undo.
  The earliest polished stock template is also recognized for upgrades; it must
  not label new/learning/relearning source words as missing. Jitendex now keeps
  modern common senses even when another sense is archaic (including `大丈夫`),
  producing 17,616 eligible forms from the pinned export. Prior suggestion caches
  rebuild automatically. Per-category vocabulary-only settings remain respected.
  Front/back example sources are independent in settings version 7. Question and
  Answer groups explain selected Anki fields versus Jitendex additions. Word flags
  keep back-only dictionary examples out of front clues and ambiguity checks;
  Recognition fronts now render their selected word examples. Existing shared
  choices migrate unchanged, with no new note fields or baseline adoption needed.
  Refresh now overwrites Katanki-managed fields, including edits and damaged or
  missing tracking, without replacement review. Legacy `UserExamples` data is
  preserved but ignored; new note types omit that field;
  enabled update options still control which fields are regenerated.
  Furigana now has independent
  front/back switches: Production defaults to both sides, Recognition to back only.
  Creation and Refresh persist escaped whole-word Jitendex readings for offline
  ruby rendering below kanji groups, including masked production clues. Kana
  anchors align mixed words; ambiguous splits retain grouped readings. Chips add
  padding when annotated; unknown readings stay plain. Standalone Qt checks
  cover UI save/reopen, real-Anki settings persistence, and offline exported cards
  with Anki-only fronts and dictionary-expanded backs.
  Verification: 377 unit tests, lint/format checks, real-Anki generation/example
  refresh lifecycle checks, and the offline packaged build pass (2026-10-24).
  Known-only filtering now applies to selected Anki words on both sides before
  front limits and production ambiguity checks. Learning, review and relearning
  snapshots qualify; new, unknown and missing states do not. Explicit Jitendex
  additions remain independent. Creation, refresh and previews share this logic;
  stored results remain portable offline. Native mobile verification is no longer
  a completion requirement; responsive webview coverage remains.
- [x] **Example furigana.** Independent front/back toggles; Production defaults
  to both sides, Recognition to back only. Offline readings appear below kanji
  groups, aligned using kana boundaries, with safe grouped fallback and adjusted
  chip spacing. Masked clues retain alignment. Unit/JavaScript checks pass.
- [x] Allow automatic card creation from selected statistics/classification lists
  (for example JLPT levels), reusing configured generation, duplicate checks,
  ignores, and creation review.
  Delivered through New kanji cards with list/group selection and live previews;
  creation requires review approval. Evidence: `scripts/smoke_list_creation.py`
  and `tests/test_creation_review.py`.
- [x] Read existing card states and review history from Anki for the dashboard.
  Anki continues to control scheduling and due dates.
  Delivered 2026-10-25: **Katanki → Statistics**, a modeless singleton with
  list/group selection, independent recognition/writing modes, state summaries,
  searchable grid and details. `anki/statistics.py` reads owned kanji notes/cards;
  details read native review logs and exclude manual reschedules from answered
  totals. Collection changes flag the timestamped snapshot for Refresh.
- [x] Aggregate unique kanji states: missing/new, learning, young, mature,
  and relearning; include retention and progress history.
  Unique kanji counts and current states are delivered. Conservative duplicate
  aggregation gives relearning priority, then new → learning → young → mature.
  Review interval ≥21 days defines mature; queue suspension/burial are separate
  flags. Detail pass rate is all recorded answers, not Anki's True Retention.
  **Statistics → History…** provides cumulative unique kanji reviewed and daily
  retention, independently for recognition/writing, with 90-day, 365-day and
  all-history views plus exact daily values. Retention uses the first eligible
  scheduled review per kanji/local day, excluding learning, relearning,
  filtered/cram and manual entries. Historical coverage is limited to available
  logs for current Katanki kanji cards; cumulative reviewed does not imply mastery.
  Evidence: `tests/test_history.py`, `tests/test_history_ui.py` and
  `scripts/smoke_history.py`. Separate Parts statistics are outside this scope.
- [x] Separate recognition and writing evidence; distinguish missing production
  notes from failed writing cards.
- [x] Select and validate an unofficial JLPT source; expose provenance/version and
  define coverage for omitted characters.
  The OpenJLPT adaptation pins revision `0d1d3410bec90bd4098a7c72de820543cb4f707c`,
  all five source JSON hashes, explicit CC BY-SA 4.0 license and upstream notices.
  [Source validation](JLPT_COVERAGE.md) compares candidates, documents 2,383 unique
  targets and keeps omitted characters outside-list without inventing levels.
- [x] Implement target registry, school-grade/Jōyō coverage and evidence-mode toggle.
- [x] Add modern JLPT N5–N1 coverage graphs after validating a source.
  The bundled `jlpt-openjlpt` canonical list drives the native per-group coverage
  bars, mature counts and selected-scope state distribution, independently for
  recognition/writing. Multi-selection gives cumulative ordered unions.
  `tests/test_jlpt_targets.py` and real-Anki/Qt `scripts/smoke_jlpt_coverage.py`
  verify counts, provenance, missing dictionary data and unchanged collection
  rows. The independent data pack is public and checksum-locked for clean builds.
- [x] Build searchable kanji grid/explorer and per-character detail pane with
  stroke links and offline stroke display/playback.
  Search by kanji, meanings or kana readings; details show both evidence modes,
  matching-card browser links, available meanings/readings and sanitized KanjiVG
  SVG with playback. Disabled/missing dictionaries do not change target totals.
- [x] Build the dashboard entirely with native Qt widgets and model/view classes.
  List/group progress bars show known percentages and mature counts in source
  order, including each elementary grade. Multiple groups use a unique union.
  Qt SVG handles offline stroke playback; no frontend build is needed.
  Overview cards use subtle theme-aware state colours with a labelled legend.
  The grid defaults to mature → young → relearning → learning → new → missing,
  with dataset order available as the other sorting option.
- [x] Add a dynamic **All kanji with cards** scope from owned recognition/writing
  cards, independent of enabled lists. Duplicate identities count once; both
  modes share membership and preserve missing-mode evidence. Refresh updates it.
- [x] Keep generated target payloads out of version control. Generate into ignored
  `dist/targets/` and restore built-ins from checksum-locked GitHub release ZIPs.
- [x] Test unique-identity counts, duplicate suppression, mixed progress, missing
  writing cards, and classification gaps.
  Evidence: `tests/test_statistics.py`, packaging/menu tests, offline Qt rendering
  (`scripts/smoke_statistics.py`) and real packaged Anki window/lifecycle checks
  (`scripts/anki_dev.py --statistics-smoke`). Desktop and compact layouts,
  light/dark, filters, groups, playback and unchanged collection tables verified.
  Cleanup verification (2026-10-25): 480 unit tests, lint/format checks, native Qt
  statistics/settings checks, full packaged Anki smoke and offline build pass.

Acceptance: polished cards work on desktop and mobile and remain studyable
offline after export/import without the add-on or source decks. Dashboard counts
match Anki evidence and never imply writing mastery from recognition alone.

## Pre-beta addition — Existing-card migration

- [x] Reviewed conversion from user-selected source decks, note types
  and character fields for recognition and production. Parts are identified from
  the character within either source, including writing with source name/meaning clues.
  Two visible source panels use skip choices, progressive controls, inline guidance
  and a destination review table; there is no separate category enable checkbox.
  Original card IDs, scheduling, FSRS data, review logs, flags, tags and decks survive.
  Cards transfer to Katanki notes; note IDs may change. Preserve unmapped sibling
  cards, and remove only empty source notes after transfer. No source archive field
  is stored; old MigrationSource fields are removed from target note types during
  conversion. Stage labels and card counts report scanning, content preparation,
  conversion and verification in Anki’s progress popup, including long-running
  dictionary loading and backup stages. Successful conversion opens Refresh to
  regenerate managed card content from the saved settings.
  Automatic collection backup, stale-preview rejection, grouped Undo and failure
  rollback are delivered. Duplicates, ambiguous fields, filtered cards and missing
  dictionary content are skipped; cloze/unencoded Parts mappings are unsupported.
  Evidence: `tests/test_migration.py`, `tests/test_migration_ui.py` and real-Anki/Qt
  `scripts/smoke_migration.py` cover preflight, source selection, split modes,
  history/scheduling, backups, archive-field removal, stage/count progress,
  stale approvals, invalid target models, Undo, partial-failure rollback,
  sibling preservation, automatic parts detection and post-migration Refresh.

## Phase 5 — Public beta

Deliverable: a documented, self-contained release for ordinary desktop Anki users.
Covers FR-06 and production readiness of the dictionary subsystem.

- [x] Provide restartable first-run setup for ordinary users.
  A collection-local setup wizard opens once Anki reaches an idle deck list.
  It guides source selection, generation destinations, automatic refresh and card
  display choices, then routes to migration or discovery. Dismissing discards
  unsaved choices and explains how to restart from **Settings → Refresh**;
  completing setup preserves advanced preferences. Profile switches and active
  dialogs/operations defer or cancel the pending prompt safely.
  Evidence: `tests/test_onboarding.py` covers scheduling, idle/profile guards,
  dismissal/restart guidance, saved settings/defaults, source/destination validation
  and migration/discovery routing.
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
    without downloading upstream again or regenerating the known bytes.
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
  Portable generated-card review and clean-profile export/import checks are
  delivered in Phase 4; the complete public-release installation/update path
  still needs offline verification.
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

- [ ] Editable user examples (`UserExamples`), user-first deduplication/ordering,
  optional readings, and live production clues after note-editor changes. Restore
  the editor field and integrate limits, masking, ambiguity checks, and previews.
  Deferred 2026-10-24: new note types omit the field; existing field contents are
  preserved but ignored by stock cards and refreshed production prompts.

- [x] FR-07: generic existing-card migration, including user-mapped Migaku Kanji GOD
  cards. Delivered before beta; see the existing-card migration addition above.
  Cloze and unencoded Parts keys remain outside the supported mappings.
- [ ] Personal-list editor under Settings → Statistics → Personal lists. Create
  and edit list names and ordered groups, paste kanji with validation and
  deduplication, and show per-group and unique-list counts. Keep source/provenance
  fields in an expandable Source details section. Save to the existing
  profile-local storage and import/export the same canonical JSON format; preview
  membership changes before replacing a saved list. Editing targets must not
  create/delete cards or change scheduling. JSON import/export is delivered in
  Phase 4; this editor removes the need to hand-edit JSON.
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
- [ ] Additional classifications: frequency and custom packs.
  Jōyō and school-grade datasets are delivered in Phase 4.
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
- [x] Finalize packaging for native dashboard resources.
  Python Qt widgets ship in the root-entrypoint archive; target datasets restore
  from locked release packs. No separate frontend assets or build are required.
