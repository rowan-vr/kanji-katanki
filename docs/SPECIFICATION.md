# Kanji Katanki ⚔️

**Kanji learning for Anki, from primitives to mastery.**

> Status: Planning / proof of concept. This document is the current implementation specification, not a claim that features already exist.

Kanji Katanki is a modular, offline-first, open-source **desktop Anki add-on** for discovering kanji in existing vocabulary, teaching their components, generating recognition and writing cards, displaying stroke order, and visualizing progress by JLPT level and other classifications. Inspired by Migaku Kanji GOD, with a cleaner data architecture and a straightforward installation experience for ordinary Anki users.

## 1. Non-negotiable design decisions

1. **Use Anki for scheduling and review history.** Kanji Katanki must not implement its own SRS or directly edit Anki's underlying collection database.
2. **Generated content is independent.** Vocabulary notes are discovery inputs, not owners of generated kanji/primitive notes. Removing source vocabulary must **never** remove, suspend, reset, or otherwise change generated material.
3. **No source-to-generated lifecycle tracking.** No parent-child relationships, cascade deletion, orphan cleanup, or continuous synchronization with source notes. Manual or automatic refresh may discover new material; refreshing examples on existing notes requires explicit opt-in and must never couple their lifecycle to source notes. Katanki note types and their character/component fields establish ownership and deduplication.
4. **Deduplicate by Katanki note type plus character/component key within the collection.** Recognition and production use separate note types, each with one card template. Production is explicitly selected per character/primitive; recognizing a character never requires generating its production note. No synthetic identity field or configuration scope is stored. Never create duplicates on rescanning.
5. **Data-driven dictionaries.** A registry of small JSON manifests describes datasets, URLs, capabilities, licensing and formats. Generic download/cache/import logic uses reusable format adapters; **do not create one bespoke Python module per dictionary** unless its file format requires a new parser.
6. **Working defaults first, customization second.** Ship a tested default dictionary stack; provider replacement is an extensibility feature, not a first-run requirement.
7. **Clear package boundaries.** Top-level feature packages are `common`, `dictionaries`, `generation`, `statistics`, `anki`, and `ui`. **No miscellaneous `modules/` directory.**
8. **Safe-by-default.** POC operations are read-only; write operations introduced later must have preview, user confirmation, idempotency and error handling. Test in a separate Anki profile.
9. **Public-user experience.** Installed users should not need Python, uv, Node.js or a separate environment. Ship a self-contained `.ankiaddon` package.
10. **Keep the POC small.** No external plugin SDK, AI features, handwriting recognition, telemetry, cloud services, or Kanji GOD migration in v0.1.

## 2. Stack and runtime

- **Anki add-on host:** Python loaded by desktop Anki; `aqt`/Qt and Anki APIs accessed only by integration/adapters.
- **Development environment:** `uv` + `pyproject.toml` + `uv.lock`; `pytest`, `ruff`, and type checking when practical. `uv` is **not** an end-user runtime dependency.
- **User interface:** Native Qt dialogs and model/view widgets for settings and statistics, including Qt SVG stroke playback.
- **Data:** JSON manifests; upstream gzip/ZIP/XML/SVG as supplied; normalized, indexed SQLite cache if useful for runtime performance. Do not build a second collection database.
- **Packaging:** `.ankiaddon`, bundled Python modules and static resources; versioned dictionary downloads or bundled data subject to licensing.
- **Platform target:** Windows, Linux and macOS desktop Anki. Explicit minimum supported Anki/Python versions to be selected after an integration smoke test. Mobile add-on support is not a goal.

## 3. Repository layout

```text
katanki/
├── src/katanki/
│   ├── __init__.py                  # Add-on entrypoint / bootstrap as packaging requires
│   ├── common/
│   │   ├── models/                 # Shared kanji, primitive, dataset and note specs
│   │   ├── interfaces/             # Protocols / contracts
│   │   ├── config/                 # Versioned configuration models
│   │   └── errors.py
│   ├── dictionaries/
│   │   ├── registry.py             # Read and validate manifests
│   │   ├── manager.py              # Dataset lifecycle and lookups
│   │   ├── downloader.py           # Fetch, validate, safely unpack, atomic updates
│   │   ├── storage.py              # Indexed normalized cache
│   │   ├── adapters/               # Shared parsers keyed by source format
│   │   │   ├── kanjidic2_xml.py
│   │   │   ├── jmdict_xml.py
│   │   │   ├── kanjivg_svg.py
│   │   │   └── normalized_json.py
│   │   └── manifests/
│   │       ├── kanjidic2.json
│   │       ├── jmdict.json
│   │       └── kanjivg.json
│   ├── generation/
│   │   ├── discovery/              # Scan note fields, tokenize and deduplicate
│   │   ├── primitives/             # Component graph and prerequisite ordering
│   │   ├── cards/                  # Recognition, writing and primitive specs/templates
│   │   └── planner.py              # Side-effect-free generation preview
│   ├── stats/
│   │   ├── aggregation.py          # Card states + Anki progress, no duplicate SRS
│   │   ├── coverage.py             # Unique-character coverage by classifications
│   │   ├── history.py
│   │   └── classifications/        # Dataset-driven JLPT, grade, frequency lists
│   ├── anki/
│   │   ├── integration.py          # Hooks and menu commands
│   │   ├── collection.py           # Read-only scan adapter
│   │   ├── notes.py                # Safe materialization in later phases
│   │   └── identities.py           # Persistent deduplication identity
│   └── ui/
│       ├── dashboard.py
│       └── statistics_widgets.py
├── tests/
│   ├── unit/
│   └── integration/
├── scripts/                         # Build/release helpers
├── pyproject.toml
├── uv.lock
└── README.md
```

**Scope discipline:** This is a target layout, not a mandate to create empty modules/files immediately. Add files when the feature needs them. `common` should contain only shared contracts, not arbitrary utilities.

### Dependency direction

- `common`: depends on no feature packages and contains **no Anki/Qt imports**.
- `dictionaries`: may depend on `common`.
- `generation`: may depend on `common` and dictionary **interfaces**; no Anki/Qt imports.
- `statistics`: may depend on `common` and dictionary/classification interfaces; consumes normalized Anki review snapshots, not live Anki objects.
- `anki`: translates real Anki collection data into core models and applies explicitly approved note-creation plans. May orchestrate other packages.
- `ui`: presents data and triggers application operations via application callbacks, without implementing dictionary, scheduling or generation logic.

No circular dependencies. Each package must be independently unit-testable where possible.

## 4. Dictionary subsystem requirements

### Default datasets

| Source | Role | Notes |
| --- | --- | --- |
| **KANJIDIC2** | Kanji readings, meanings, stroke counts and character metadata | Default kanji dictionary |
| **JMdict** | Vocabulary readings, glosses and other lexical data | Needed for vocabulary-aware prompts in a later phase |
| **KanjiVG** | Stroke vectors/order, groupings, component structures | Default visual/stroke source; mnemonic primitive names may need another curated source |
| **Community JLPT dataset (TBD)** | N5–N1 classification | Unofficial; always display provenance/version |

### Manifest-driven design

- Small JSON manifest per dataset: stable ID, display name, format adapter identifier, source URL(s), archive/compression type, capabilities, version/checksum mechanism, license/attribution metadata, and whether it is a recommended default.
- Manifests contain **metadata**, not the entire dataset. Local downloaded/bundled archives remain separate from normalized indexes.
- Reuse parsers for shared formats. A new dataset using an existing normalized schema should require only a manifest and data files.
- Data manager provides `list_datasets`, `install/update`, `status`, and lookup functions; consumers use normalized models, never dataset-specific XML/JSON.
- Downloads use HTTPS, validate source and archive content, prevent zip-slip/path traversal and decompress-bomb problems, and switch caches atomically. A failed import must leave the last working dataset intact.
- Runtime lookups must work offline once installed. Define first-run bootstrap behavior before public beta (bundled essential data or clear optional download step).
- Support provider/capability selection **later**, with tested defaults. A provider switch must not silently rewrite Anki cards.
- Review upstream licensing, per-field restrictions, redistribution obligations and attribution **before** bundling or publicly redistributing data.

A manifest might have `id`, `category`, `format`, `source`, `capabilities`, `license`, and `default`; schemas must be validated. Avoid treating downloadable manifests as executable code.

## 5. Functional requirements

### FR-01 — Discovery

- User can select target decks, note types and fields; scan only selected sources. Phase 2 uses selection for the current run; Phase 3 adds source configuration in the add-on settings and persistence across restarts.
- Extract kanji code points, deduplicate at character level and report them; do not indiscriminately treat all CJK ideographs as supported Japanese kanji.
- Preview total scanned notes, distinct kanji, existing Kanji Katanki kanji and missing kanji. Report unsupported/no-dictionary entries separately.
- Support manual kanji text entry using the configured discovery-to-generation workflow.
  Imported lists remain a future enhancement.
- Scanning is **read-only**; no source edits, tags or deletion. The later refresh workflow orchestrates scanning and separately approved generation; scanning itself never writes notes.

### FR-02 — Primitive graph

- Discover graphical components from the selected decomposition dataset, with deterministic deduplication.
- Maintain an acyclic prerequisite graph, detect cycles/missing nodes and produce a stable learning order.
- Distinguish graphical components from dictionary radicals, whole kanji, and user-facing mnemonic names.
- Users may enable/disable primitive prerequisites and later customize names or exclusions.
- Primitives need not all be independently encoded Unicode characters; assign stable Kanji Katanki identities.

### FR-03 — Generation

- Generate permanent **Kanji Katanki-owned** notes for recognized kanji and optional primitives from the selected vocabulary sources.
- Use separate recognition and production note types for kanji and primitives, each with one card template and native independent Anki scheduling. Generate only the modes explicitly selected for each character/primitive; production is opt-in.
- Recognition: character → meaning/reading, with optional front examples. Kanji
  production uses dictionary meanings and optional masked examples; blank every
  occurrence of the target (`時間` → `__間` for `時`). Choose production with a
  checkbox, without entering a manual prompt. Validate the final visible clues
  after example visibility and limits are applied; report missing/ambiguous clues
  as unavailable. **Vocabulary writing** remains a separate optional template:
  reading + meaning/context → full written word, accounting for homophones.
- Store every eligible selected-vocabulary example, including single-kanji words,
  independently of how many examples are displayed. Vocabulary comes from the
  sources configured under Discovery; default dictionary examples are an optional
  additional source planned via Jitendex in a follow-up PR. `真ん中` supplies examples
  for `真` and `中`, not `間`.
- Example fields and rendering follow the
  [card example design](CARD_EXAMPLES.md): Katanki-managed `VocabExamples`,
  deduplication, stable ordering,
  and a per-category display limit of 5 by default (0 means show all). Store all
  eligible examples. Configure front and back sources independently: selected Anki
  words only, or Anki words plus Jitendex dictionary words. Preserve legacy shared
  choices during settings migration. Store side eligibility on the note so exported
  cards work independently. Back-only dictionary words must not enter front clue
  generation, refresh, or ambiguity checks. Visibility and limits control front clues only. Backs show all
  configured stored examples sorted known → relearning → learning → new → no card,
  using blue, rose double-border, amber dashed-border, plain-outline, and gray chips
  respectively. Show the total unique count; long lists may display 12 chips plus
  an expandable remainder, without discarding words. Save statuses from configured
  source cards during creation/refresh;
  learned means at least one matching card has graduated into Anki review. These
  snapshots must work independently of source decks and the add-on. Use distinct
  front/back layouts without instruction prompts or repeated front content.
  Production masks the target
  in managed examples. Parts uses example kanji containing the part,
  on the back, rather than vocabulary words. Keep meanings and examples separate
  from the production prompt representation. Remaining example display work,
  reviewed-only filtering resolves selected Anki word states at creation/refresh. Furigana with kana-anchored
  alignment is delivered; editable user examples are deferred to Phase 6.
- Preserve source deck data; no source-to-generated lifecycle tracking.
- Review cards must be self-contained and responsive on desktop Anki, AnkiMobile,
  and AnkiDroid, including after deck export/import. Include required templates,
  styles, scripts, and media so study works offline without the add-on, installed
  dictionaries, a local server, or source vocabulary decks. The add-on provides
  easy creation and refresh; existing cards do not require it for study.
  Resolve source-dependent example filtering during creation or refresh and
  retain the data needed for independent review on the notes.
- Deduplicate by NFC-normalized character/component key within its Katanki note type, **not** by note ID or source vocabulary origin. Store the character or component key directly; no synthetic identity field or configuration scope. Make reruns idempotent.
- Before writes, show a detailed plan (create/skip/unavailable) and require explicit approval. Phase 3 must define how saved approval choices support one-button and automatic refresh while retaining these safeguards; saving source settings alone does not authorize writes.
- Preserve all existing Kanji Katanki note IDs, card IDs, scheduling and review history on rerun. Do not overwrite user edits without opt-in.
- Deleting source vocabulary must not change generated kanji/primitive cards, even when no other source contains the character.

### FR-04 — Stroke-order learning

- Present KanjiVG SVG, stroke numbers, animated playback and relevant components when available.
- Accessible on card backs and in kanji detail viewer; offline-ready and resilient to missing SVGs.
- Manual handwriting on paper is supported by production cards; **automatic recognition of handwritten strokes is out of scope**.

### FR-05 — Statistics

- Kanji GOD-like progress dashboard: unique kanji and primitive counts, unseen/learning/young/mature/relearning statuses, retention and progress over time.
- **Separate recognition and writing metrics**; a recognized character must not count as handwriting-mastered unless corresponding writing evidence exists.
- N5–N1 JLPT coverage by versioned unofficial dataset; other classification packs (Jōyō, school grade, frequency lists) later.
- Allow automatic card generation for selected statistics/classification lists (such as JLPT), using the saved generation settings and creation safeguards.
- Interactive searchable kanji grid with per-character details and stroke links.
- Calculate counts on **unique identities**, not the number of vocabulary occurrences or review cards.
- Derive review state from Anki data; no shadow scheduler. Clearly distinguish characters without a production note from failed writing cards.

### FR-06 — Settings and distribution

- After Phase 2 generation and card content work end to end, deliver a dedicated
  UX phase before the statistics dashboard.
- Configure and save vocabulary sources (decks, note types and fields) in the
  add-on settings, together with generation preferences and recommended defaults.
  Settings persist across Anki restarts; provider customization remains later work.
- Provide one refresh button that loads saved settings, scans configured sources,
  previews/plans generation and runs the approved workflow without repeated setup.
- Support automatic refresh with configurable triggers and clear enabled/disabled
  controls. Reuse the manual refresh workflow, saved settings and write safeguards.
- Define explicit opt-in behavior for updating vocabulary examples on existing
  generated notes. Preserve user edits, note/card IDs, scheduling and review
  history; removing vocabulary must never trigger destructive changes.
- Show progress, results and actionable errors, including missing or invalid source
  settings. Repeated manual or automatic refresh must remain idempotent.
- Versioned configuration with safe migrations; standard Anki add-on installation and clear errors if datasets are absent.
- No telemetry, accounts, cloud services or network-required review flows by default.
- Ship a self-contained `.ankiaddon` on AnkiWeb/GitHub; cross-platform smoke tests and documentation.

### FR-07 — Legacy import (post-beta)

- Optional explicit migration or recognition of existing Migaku Kanji GOD notes; migrate scheduling/review history only with a proven safe mapping.
- Never auto-convert existing notes. Always require backup, dry-run mapping, warning for unmappable data, confirmation and tests on a copied Anki profile.

## 6. Development phases & acceptance criteria

### Phase 0 — Bootstrap (first task)

**Deliverable:** Add-on installs in a separate Anki desktop test profile; `Tools → Kanji Katanki → Analyze Collection` displays a basic dialog.

- [x] Create `uv` project with `pytest` and `ruff`, reproducible lockfile.
- [x] Make Anki-compatible add-on entrypoint and menu integration.
- [x] Add logging and graceful failure handling.
- [x] Add unit test and documented local install/build procedure.
- [x] Confirm targeted Anki/Python versions using actual smoke test.

**Verified baseline (2026-10-22):** Linux desktop Anki 26.09.3 / Python 3.14.8.
The packaged add-on passed an isolated real-host smoke test for menu registration,
dialog display, per-add-on logging, and unchanged note/card counts. Python unit
tests run on 3.12.14. Older Anki versions and Windows/macOS host compatibility are
not established by this milestone.

### Phase 1 — Read-only discovery and dictionary POC

**Deliverable:** Select scan fields, detect unique kanji, and inspect dictionary/stroke data without mutating collection.

- [x] Vocabulary scanner as pure Python plus Anki read adapter.
- [x] Registry and validated manifests; load KANJIDIC2 and KanjiVG using shared interfaces.
- [x] Preview candidate/supported kanji counts, missing data, and sample stroke SVG.
  Existing/missing recognition counts are now connected to the Phase 2 note-type
  and character-field detection; without a dictionary they remain unassessed.
- [x] Verify the scan changes zero notes/cards; unit tests for token extraction and dedup.
- [x] Document how to fetch/prepare sample datasets without checking unreviewed data into repo.

**Time-box:** Target a 1–2 hour AI-assisted first POC for Phase 0 and a limited slice of Phase 1. This is an aspiration, not a release commitment; avoid scope creep.

**Verification (2026-10-22):** Linux Anki 26.09.3 / Python 3.14.8 passed the
packaged source-selection/report/SVG UI check with exact notes/cards/revlog
preservation. Official KANJIDIC2 and one KanjiVG SVG were also parsed locally,
without bundling data. See [dataset setup and evidence](DATASETS.md).

### Phase 2 — Primitives + safe card generation

**Deliverable:** Generate independently scheduled notes from selected vocabulary
sources after a preview and consent, with masked vocabulary examples and kanji
meanings on production card fronts. Saved source settings and streamlined refresh
follow in Phase 3.

- [x] Select vocabulary sources for the current generation run.
- [x] Populate production card fronts with the kanji meaning and all matching
  vocabulary examples, masking each occurrence of the asked kanji with `_`.
- [x] Note-type plus character/component-key deduplication and existing-note detection.
- [x] Component extraction, cycle checks and stable dependency order.
- [x] Separate kanji/primitive recognition and production note types, with production explicitly selected per character/primitive.
- [x] Planner produces create/skip/unavailable outcomes without performing writes.
- [x] Anki adapter applies approved plans safely and idempotently.
- [x] **Critical test:** add `景色`, generate `景` and `色`, delete `景色`, rescan. Generated notes, card progress and due dates remain untouched; no duplicate notes.

**Verified 2026-10-22:** real-host lifecycle, packaged preview approval/cancellation,
all four separate note types and offline webview stroke controls pass locally.
Kanji production automatically copies dictionary meanings and blanked source-word
examples into independent notes. Persistent source settings are the next step. See the [roadmap](ROADMAP.md) for evidence and remaining checks.

### Phase 3 — UX, saved settings, and refresh

**Deliverable:** Once Phase 2 works end to end, configure sources and preferences
once, then run all configured steps with a refresh button.

- [ ] Add source configuration and saved generation preferences to add-on settings.
- [ ] Persist versioned settings across restarts, with defaults and safe migrations.
- [ ] Implement one-button refresh using saved configuration and generation safeguards.
- [ ] Add configurable automatic refresh using the same workflow and clear controls.
- [ ] Define saved approval and explicit opt-in example-update behavior, preserving
  user edits and generated-note independence.
- [ ] Present progress, results and actionable errors without repeating setup.
- [ ] Verify restart persistence, duplicate-free repeated refreshes and unchanged
  note/card identities, scheduling and review history for existing cards.

### Phase 4 — Statistics and modern interface

**Deliverable:** Polished, portable review cards and a Kanji GOD-style dashboard
with real Anki progress.

- [x] **Polish card layouts.** Improve recognition, production, and Parts layouts
  for desktop and mobile, and complete the remaining
  [card example design](CARD_EXAMPLES.md), including
  seen/new filtering, display
  controls, preview parity, and acceptance coverage. Verify offline study on
  desktop and responsive mobile-sized webviews, plus export/import into a clean profile
  without the add-on or source decks, including required media and stroke controls.
- [x] Example furigana: independent front/back toggles, mode-specific defaults,
  offline kana-anchored alignment below kanji groups, and adjusted chip spacing.
- [x] Read existing card states and review history from Anki for the dashboard;
  Anki continues to control scheduling and due dates.
- [x] Versioned target-list contract and registry with ordered groups, exact
  character identities and unique unions. Built-ins reuse dictionary dataset
  manifests, release packs, updates and offline fallback; personal JSON uses the
  same reader. Separate elementary-school-grade and full Jōyō datasets are
  explicitly generated from KANJIDIC2 and versioned independently of runtime dictionaries.
- [ ] Personal target-list import/selection UI and persistent storage.
- [ ] Sourced/versioned unofficial JLPT dataset using the shared target-list format.
- [ ] Coverage graphs and recognition/writing mode toggle.
  Current list-state distribution and mode toggle are delivered; historical
  progress and JLPT coverage charts remain open.
- [x] Searchable kanji explorer + detail pane.
- [x] Native Qt statistics dashboard with per-list and per-grade coverage.
- [x] Tests for counts, duplicate suppression, mixed progress and missing writing cards.

### Phase 5 — Public beta

**Deliverable:** Installable and documented release usable by people without development tools.

- [ ] Verify Phase 3 settings and migrations for release; finish simple setup,
  recommended dictionary defaults and dataset bootstrap/update UI.
- [ ] Packaging and installation test on Windows/macOS/Linux.
- [ ] Error handling for missing data, malformed files, version mismatch and interrupts.
- [ ] Performance testing on realistically large Anki collections.
- [ ] Attribution/licensing review, README, screenshots, changelog, release pipeline.
- [ ] Add-on verified not to corrupt or mutate unrelated notes; backup guidance.

### Phase 6 — Optional enhancements

- [ ] Editable user examples, user-first ordering/deduplication, and live production
  clues after editor changes. Preserve existing `UserExamples` data while deferred;
  new note types omit the field and stock review/refresh ignores its contents.

- [ ] Migaku Kanji GOD migration with safe progress preservation.
- [ ] Personal-list editor: create/edit list names and ordered groups, paste kanji
  with validation/deduplication and group/unique counts, and keep provenance in
  expandable Source details. Reuse profile-local storage and canonical JSON
  import/export; preview membership changes before replacement. Saving a list
  does not create/delete cards or change scheduling.
- [ ] More dictionary providers, fallback selection, custom classifications.
- [ ] Enhanced stroke animation and optional handwriting canvas/validation.
- [ ] Public third-party extension API only after internal interfaces stabilize.

## 7. Parallel development contracts

| Agent | Owns | Can start | Should not own |
| --- | --- | --- | --- |
| **A — Anki host** | `anki/`, bootstrap, packaging, test-profile integration | Immediately | Parsing dictionaries, core kanji algorithms |
| **B — Dictionaries** | `dictionaries/`, manifests, format adapters, canonical data models proposed via `common/` PR | Immediately | Collection writes, generation strategy |
| **C — Generation** | `generation/`, graph and generation planning, card specifications | Once shared model contracts agreed | Direct `aqt` calls, UI |
| **D — Statistics/UI** | `stats/`, `ui/`, classifications | Models/fixtures now; UI after Phase 1 | Direct Anki database writes, SRS implementation |

**Before agent parallelization:** agree on `KanjiEntry`, `PrimitiveEntry`, `DatasetManifest`, `ScanResult`, `GeneratedNoteSpec`, `ReviewSnapshot`, and provider protocols. Use JSON fixtures for independent tests. Cross-package changes require review; keep pull requests small. Do not let agents create competing abstractions or duplicate the same models.

## 8. First-session checklist

1. Create repository and isolated Anki test profile (backup any existing test data).
2. Set up `uv`/pytest/ruff; create only package files needed for Phase 0.
3. Implement menu command and smoke test it in the real host Anki.
4. Add pure-Python kanji extraction and tests (`景色`, `少数民族`, kana-only, punctuation, mixed scripts).
5. Add a simple read-only scan report.
6. Introduce the manifest registry and one dictionary lookup fixture; then wire up KanjiVG preview.
7. Demonstrate that the collection remains unchanged after scanning.

**Definition of success:** Kanji Katanki can discover kanji from a sample vocabulary deck, show distinct counts and dictionary/stroke data, and exit without modifying a single note.

## 9. Open decisions (do not silently guess)

- Exact Anki desktop version(s) and matching Python runtime to support.
- Licensing and redistribution restrictions for each third-party dataset and field (Kanji Katanki code uses the MIT License).
- Dataset bootstrap strategy: **resolved 2026-10-22** at the user's request.
  Download/prepare the essential KANJIDIC2 subset and pinned KanjiVG data at build
  time, keeping payloads out of Git, and bundle them with license copies,
  attribution, versions/checksums, and an explicit maintainer refresh procedure.
  First use is offline. Independent compatible dictionary updates use a small
  online catalog and versioned GitHub Release packs; Settings retains bundled
  fallback and local/disabled sources. Additional providers/per-character assets
  remain later work.
- Source and validation of unofficial JLPT levels; meaning of “coverage” when a dataset omits characters.
- Kanji production fronts: **resolved**, extended 2026-10-23. Use kanji meanings
  with configurable masked examples. Store all eligible managed vocabulary
  examples with a default front limit of 5 (0 = all). Editable user examples
  are deferred to Phase 6. Validate the visible clues after filtering/limits. Explicitly
  enabled example refresh preserves user content and review progress. See
  [card example design](CARD_EXAMPLES.md). Jitendex default example-word support is deferred to a separate PR.
- Primitive naming system and component-vs-radical distinctions.
- Add-on folder/packaging approach for `src/` layout and native dashboard resources.

---

**Guiding principle:** *Discover once. Learn independently. Track accurately. Never destroy progress.*
