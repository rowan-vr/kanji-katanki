# Phase 4: target lists and kanji statistics

Planning baseline: 2026-10-24, branch `feat/phase-4-kanji-stats`.
The target-list foundation and first dashboard are delivered. Primitive statistics,
historical progress/retention charts, and creation from lists remain later slices.

## Target-list contract

A target list describes what someone wants to study, independently of their
collection, dictionary coverage, or review progress. It must load without Anki.
Use a versioned UTF-8 JSON format shared by bundled and user-imported lists.
Keep the format generic: no JLPT-specific fields or hard-coded level ordering.

Implemented v1 example (illustrative membership, not a published syllabus):

```json
{
  "schema_version": 1,
  "id": "user:example-course:edition-1",
  "title": "Example course, first edition",
  "version": "2026-10-24",
  "kind": "textbook",
  "source": {
    "title": "Personal course list",
    "url": null,
    "revision": "1",
    "license": "User supplied; redistribution not established",
    "attribution": "Personal study material",
    "authority": "user"
  },
  "groups": [
    {"id": "chapter-1", "title": "Chapter 1", "characters": ["日", "月"]},
    {"id": "chapter-2", "title": "Chapter 2", "characters": ["月", "火"]}
  ]
}
```

- `id` is a stable, namespaced identity; `version` identifies its content release.
  Different textbook editions receive different IDs. Schema and content versions
  are independent. `kind` is descriptive, not an enum that blocks new list types.
- Groups have stable IDs and explicit array order, supporting levels, grades,
  chapters, lessons, or a single ungrouped list. Membership can overlap.
- A group's characters preserve source order. Duplicate members within a group
  are removed with an import warning; aggregate membership is an ordered union.
  The example above has three unique targets, not four.
- Selecting several groups means union. A future cumulative-level toggle selects
  the appropriate ordered groups explicitly; never infer hierarchy from titles
  or assume every source orders beginner to advanced.
- Preserve exact character identities. Do not use NFKC to merge compatibility
  forms or silently substitute dictionary variants. V1 accepts one supported Han
  code point per member (plus `〇`, matching discovery); reject words, HTML, kana, and variation sequences with a
  useful group/member location. Align validation with discovery's Unicode policy;
  broaden that policy deliberately if a real target source needs more coverage.
- Keep valid targets missing from the installed dictionary. Report unavailable
  dictionary/stroke data separately; these targets still belong in denominators.
  Characters outside the selected target union are outside-list, not missing.
- Parse strictly: reject unsupported schema versions, duplicate JSON keys,
  malformed metadata, duplicate group IDs, and invalid members before installation.
  Empty groups are allowed; an entirely empty list is rejected. Bound file size
  and member count. Treat all display text as plain text and escape in the UI.
- Source metadata distinguishes official, unofficial, and user lists. Bundled
  lists require a source URL, pinned revision, redistribution permission, notices,
  and a content checksum. A private user list can have no URL or known license;
  importing it does not establish permission to bundle or publish it.

## Module and persistence boundaries

Implemented boundaries:

- `src/katanki/stats/targets.py`: immutable list/group/source models, validation,
  JSON serialization, ordered unions, and registry. Pure Python, no Qt/Anki imports.
- `src/katanki/stats/sources.py`: assemble classifications from selected datasets.
  `load_target_registry(choices=...)` uses existing dataset source preferences;
  bundled defaults, verified installed updates, local overrides and disabling all
  use the dictionary system. Multiple target providers coexist in `TargetRegistry`,
  while `DictionaryManager` keeps singleton dictionary lookup providers and ignores
  target-only datasets.
- `src/katanki/dictionaries/adapters/target_lists_json.py`: canonical JSON format
  adapter, available to the shared manifest, pack, install and build validators.
  Each independent dataset contains one list with arbitrary ordered groups;
  register several datasets to expose several lists. `bundled.entries` counts
  unique characters, not summed group membership. Published packs require source
  URL/checksum and non-user provenance, and reject duplicate-member warnings.
- Settings → Statistics → Lists controls support the canonical format, including
  local JSON, validation results, version/attribution, updates and bundled fallback.
  The independently versioned `school-grades` and `joyo` datasets are bundled by default.
  Dictionaries excludes target lists. Both pages reuse `ui/datasets.py` and the
  existing dataset preferences; no configuration migration is needed. Update
  offers are scoped to the current page; the daily check schedule is shared.

- Built-in lists use shared dataset manifests, license notices, release catalog,
  checksum-locked build packs, atomic installation and offline fallback. There is
  no separate list download/update mechanism. Independent list packs retain their
  pinned contents when dictionary sources are regenerated.

Personal import and selection are delivered:

- `src/katanki/anki/target_lists.py`: profile-aware personal import storage,
  canonical JSON export, explicit replacement and removal.
- `src/katanki/ui/target_lists.py`: **Settings → Statistics → Personal lists**,
  with import review, group/unique counts, provenance, validation warnings and
  explicit replacement showing added/removed members. Source dataset management
  remains in **Statistics → Lists**; group selection lives in the dashboard.
- Personal lists live under profile-keyed add-on `user_files`, outside files
  replaced by add-on updates. Profile identity uses the collection directory;
  moving a profile to another directory requires exporting/importing its lists.
  Settings version 8 persists selected list/group IDs. Personal lists join the
  same registry as bundled lists and remain usable without dictionary coverage.

The registry rejects ID collisions rather than silently replacing bundled data.
Personal imports validate fully before atomic installation. Reimporting identical content
is a no-op; changed content with the same ID gets a preview of added/removed
members and requires an explicit replacement action. Lists do not create notes,
change scheduling, or delete notes when targets are removed. Profile-specific
files do not automatically sync across devices; export/import JSON to transfer them.
Import, replacement and removal apply immediately after confirmation. Cancel in
Settings does not undo these file operations; the Personal lists page states this.

## First sources and delivery slices

1. **Canonical contract and registry — delivered.** Models, strict JSON loader,
   ordered selection/union, round-trip export, and actionable validation. Test
   overlap, ordering, supplementary Han, exact variants, invalid members, unknown
   schema, malformed metadata, collision handling, and dictionary-independent totals.
2. **First bundled source: school grades and Jōyō — delivered as separate datasets.** Use the pinned bundled
   KANJIDIC2 grade metadata through an adapter, retaining its source revision and
   notices. Grades 1–6 represent elementary groups; grade 8 is the remaining
   secondary-school Jōyō group. Name this a KANJIDIC2-derived classification.
   Verify actual membership/counts against a current authoritative reference
   before claiming current official coverage. Never include grades 9/10 as Jōyō.
   `scripts/generate_target_lists.py` explicitly generates canonical JSON from a
   chosen KANJIDIC2 snapshot. The shipped lists are version 2026-10-25, derived
   from KANJIDIC2 2026-10-23. `school-grades` contains 1,026 elementary-school
   targets in six grade groups. `joyo` contains the full 2,136-target set as one
   group, including those 1,026 plus 1,110 secondary-school targets. Each has its
   own manifest, version, source checksum and release pack. These are separate
   UI entries; selecting both still counts each character once.
   Runtime loading reads only the canonical list; dictionary updates, disabling
   dictionaries, or changing dictionary coverage do not change target membership.
   Regeneration is an explicit maintainer action, independent of dictionary refresh.
3. **Personal import and selection — delivered.** JSON file import/export and
   target-list management preview groups, total unique targets, source/version,
   and validation warnings before installing. Restart/profile isolation,
   safe replacement and offline packaging are verified. A later plain-text/CSV
   adapter can create the same canonical model without expanding the core format.
4. **Modern JLPT source investigation.** Compare candidate N5–N1 datasets for
   provenance, license, update stability, overlaps, and coverage; pin one known
   revision. Label it unofficial. KANJIDIC2's old four-level JLPT field cannot
   supply modern N2/N3 membership. Do not synthesize modern levels from it.
5. **Additional sources.** JPT and textbooks use the same import contract when
   reliable membership is available. Do not invent a syllabus or assume an exam
   publishes kanji levels. Textbooks retain edition/chapter identity.

Acceptance for the current scope: at least one real bundled classification plus
one imported personal list work through the same registry; group selection gives
stable, deduplicated targets offline; provenance is visible; import/restart and
packaging checks pass; collection note/card counts remain unchanged. The current
change delivers the backend contract, separate built-in datasets, shared pack
integration, personal import persistence and list/group selection UI.

Personal-list verification (2026-10-25): `tests/test_personal_target_lists.py`
checks canonical export, profile isolation, atomic installation failures,
identical-content no-op, stale previews and explicit replacement. Dashboard tests
cover personal-list registration and persisted group selection.
`scripts/smoke_personal_target_lists.py` passes against real Anki/Qt with a
disposable collection: import and replacement cancellation/confirmation, member
diffs, plain-text provenance, export, removal cancellation/confirmation, reopened
storage, profile isolation, rejected imports and unchanged notes/cards/revlog.
`uv run python scripts/build_addon.py --offline` passes; private `user_files`
contents are excluded from the add-on package. On Linux desktops using KDE/fcitx,
the standalone headless smoke command is:

```bash
QT_QPA_PLATFORM=offscreen QT_QPA_PLATFORMTHEME= QT_IM_MODULE=none /usr/bin/python scripts/smoke_personal_target_lists.py
```

## Where statistics should appear

Investigation supports the following options; the recommendation is a dedicated
window first. These are proposed UI decisions, not delivered integrations.

| Surface | Strength | Constraint | Recommendation |
| --- | --- | --- | --- |
| Katanki → Statistics window | Room for target/group selector, recognition/writing toggle, coverage, searchable grid and detail pane | Another window to open; must refresh after collection changes | Primary dashboard, resizable native Qt window with list and grade coverage |
| Main deck screen | Frequent visibility; Anki exposes a content hook | Large grids distract from deck selection; collection scans must not block rendering | Later optional compact summary linking to the dashboard |
| Native Anki Stats window | Familiar stats entry point and deck/search scope | Unique target kanji differ from native card counts; integration needs host-version verification | Investigate a summary/link after the dedicated window works |
| Deck overview | Useful for a selected deck | Targets can span several decks; must make scope clear | Optional later shortcut or scoped summary |
| Reviewer | Immediate character context | Interrupts study and adds review-time overhead | Keep review cards portable; use the dashboard/detail pane for statistics |

The Katanki menu opens the native Qt dashboard. Optional future deck-browser
summaries would need separate host integration; the dashboard itself uses Python
callbacks and Qt signals.

The initial dashboard should show selected target/group, unique target total,
state distribution, missing-card count, and a grid that opens character details.
Dictionary gaps and list provenance must be inspectable. A group view and a
cumulative selection use the same target-union operation defined above.

## Progress policy

Prefer Anki's native states rather than new configurable thresholds. Anki defines
mature as review interval ≥21 days; young is a review card below that boundary.
Keep learning and relearning distinct, and distinguish an existing new card from
a target with no matching card. Suspension/burial are availability flags rather
than evidence of forgetting. Avoid a standalone “known” state; if added later,
label it as a derived summary with an explicit definition.

Native card state does not define a unique-kanji aggregation policy. The dashboard
uses the conservative policy described below for conflicting states; suspended
and buried cards keep their learning state. Manual reschedules are excluded from
recorded-answer pass rates.
Keep recognition and production evidence independent; source vocabulary exposure
is separate evidence and must not imply successful writing. Do not reuse the
example-chip `WORD_STATUS_ORDER` as a mastery model. Target lists store no progress state; the dashboard derives it from the collection.

## Sources consulted

- [Anki statistics manual](https://docs.ankiweb.net/manual/stats): card/review
  statistics, native maturity boundary, and extension possibilities.
- [Anki GUI hook definitions](https://github.com/ankitects/anki/blob/main/qt/tools/genhooks_gui.py):
  `deck_browser_will_render_content`, `webview_will_set_content`, and
  `webview_did_receive_js_message`; verify against the supported release at implementation.
- [JLPT FAQ](https://www.jlpt.jp/sp/e/faq/): modern test content lists are not published.
- [KANJIDIC documentation](https://www.edrdg.org/wiki/KANJIDIC_Project.html):
  grade classifications and legacy JLPT field semantics. This local documentation
  copy warns that some material may be out of date; validate the pinned data.

## Delivered dashboard (2026-10-25)

Open **Katanki → Statistics**. This is a separate modeless window; Settings →
Statistics → Lists continues to manage source datasets. The dashboard offers list
and group selection, recognition/writing modes, unique state counts and a coverage
bar, text/state filters, and a kanji grid with details. Search includes available
meanings and readings; kana search treats hiragana/katakana equivalently.

Statistics cover owned Katanki recognition/production notes across the collection,
not vocabulary exposure or unmarked note types. Each target counts once per mode.
Missing cards differ from new cards, and the detail pane distinguishes absent
notes from notes without cards. Current card type determines learning/relearning;
review intervals ≥21 days are mature. Mixed evidence conservatively prioritizes
relearning, then new, learning, young and mature. Suspension/burial are availability
flags, displayed separately. This policy does not modify scheduling.

Details show both modes, matching-card browser actions, dictionary readings and
meanings, and sanitized offline SVG/playback when available. Pass rate means all
recorded answers across matching cards, excluding rating-zero manual operations;
it is not Anki's first-answer-per-day True Retention metric. Deleted cards do not
contribute evidence. Historical charts and primitive classification are not yet
implemented. Missing/disabled dictionaries never remove valid targets.

The interface uses native Qt widgets in `ui/dashboard.py` and
`ui/statistics_widgets.py`: a list/group tree, progress bars, a model/view kanji
grid, detail labels and Qt SVG playback. Each list and school grade shows known
(young + mature) coverage and mature counts for the chosen mode. Multiple selected
groups form a unique union. List and group order follows the source dataset. The
**All kanji with cards** scope is generated from owned recognition/writing cards,
independent of enabled datasets; both evidence modes share its membership.
The grid defaults to mature → young → relearning → learning → new → missing,
with source list order as the other sorting option. Overview cards use subtle
state tints matching the grid and its labelled legend.
Collection operations mark the snapshot stale; Refresh reloads it. Closing the
window/profile removes hooks and stops animation. Reopening reuses the window.

Verification: progress tests and real-Anki fixtures cover duplicate cards,
maturity boundaries, missing writing, invalid/missing data and unchanged
notes/cards/revlog. `scripts/smoke_statistics.py` checks native widgets at desktop
and compact widths in light/dark modes, including grade coverage, search, details
and stroke playback. `scripts/anki_dev.py --statistics-smoke` verifies the packaged
window and lifecycle in an isolated profile. No Node build or web assets are needed.
