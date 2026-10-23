# Card examples

Phase 3 design, partially implemented. Creation and Refresh now store managed
suggestions in `VocabExamples` and protect `UserExamples`. Recognition and Parts
show examples on the back. Production uses a generated `Prompt` snapshot rebuilt
on Refresh, merging user examples first, deduplicating, limiting, and masking all
target occurrences. Settings control default words, visibility and limits.
Furigana, seen/new filtering and live production-front rendering after an editor
change remain pending; refresh applies user-example edits to production clues.
Exact previous stock templates are upgraded during creation or approved migration;
customized templates are preserved.

## Fields

| Field | Content | Updated by |
| --- | --- | --- |
| `VocabExamples` | Examples from vocabulary sources and optional default words | Katanki refresh |
| `UserExamples` | Extra examples entered in the note editor | The user only |

Store examples separately from meanings instead of combining them in `Prompt`.
Store the original words; mask the target kanji when rendering production fronts.
Keep source information with managed examples so vocabulary words and defaults
can be filtered separately.

Recognition and Production use vocabulary words. Parts uses kanji containing
the part and shows them on the back. Showing the part's name on the front is a
separate setting.

## Display

Each category has an example limit: **5 by default**, **0 for all**. Store all
eligible examples on the note and apply the limit when rendering.

Show user examples first, followed by managed examples. Remove duplicates before
applying the limit, keeping the user's version. Preserve user ordering and keep
managed examples in a stable order. Both fields count toward the limit.

Recognition and Production respect the example visibility, source, furigana,
and seen/new settings. Parts has no furigana or word review-status filter.

Production masks every occurrence of the target kanji in both fields without
changing the stored text. Check for ambiguous production clues after filtering,
masking, and limiting: an example that isn't shown cannot distinguish two cards.
Previews and actual cards must render the same content.

## Refreshing existing cards

Settings → Refresh saves a global **Update example words** switch (default on)
for manual and automatic refresh. Each category's automatic-example-refresh
setting also controls its managed examples and defaults to on; both must be
enabled for updates. When refresh runs automatically is configured separately.
Both manual Refresh and configured automatic triggers apply these preferences.
Example updates run as an Anki CollectionOp after a read-only planning scan, even
when no new cards are created or the selected source vocabulary has disappeared.
Disabling card generation does not disable example updates; use the refresh switches.
Manual kanji entry only plans creations and does not refresh unrelated existing notes.

Refresh also saves **Update tags from source vocabulary** (default off), separate
from example updates. Tags must remain unchanged when this switch is off. Safe
handling of source-derived versus manually added tags still needs implementation.

Refresh never changes `UserExamples`. For managed fields, compare the current
value with the last generated value before updating. Leave manual edits intact
and report conflicts. New notes record last-generated example values in
`KatankiExamplesState`, including managed examples, display limit, attribution and
kanji production clues. Older notes with no baseline require a manual migration
review showing the exact before/after fields. Cancel preserves legacy notes;
automatic refresh never approves migration. Malformed baselines and duplicate
owned identities are preserved and reported. Customized templates are left intact.

Before applying, Refresh checks for changed source vocabulary/settings, changed
note fields, ownership, and production-clue collisions. Stale results are skipped
and reported. Baselines are written with the managed fields, so repeated refreshes
are no-ops and interrupted updates can resume safely. Example updates never change
meanings, readings, strokes, mnemonic names, tags or decks.

Updates use Anki APIs and support Undo. Preserve note/card IDs, scheduling,
review history, and decks. Preserve tags unless source-tag updates are enabled. Removing source vocabulary must never delete a
generated note.

Updates that would leave production clues empty or ambiguous preserve the current
managed examples and clues and report a conflict. Collisions are checked against
other current production notes and the proposed batch after masking and limiting.
Recognition and Parts can clear managed examples after source removals; generated
notes/cards are never removed. Jitendex remains available offline for defaults.

## Default words

Builds include the complete Jitendex Yomitan archive plus a lightweight suggestion
index from the pinned
2026.10.03.0 Yomitan export. `datasets/jitendex-lock.json` records its immutable
release URL, source and generated SHA-256 checksums, version, and attribution.
The export was inspected before implementing conversion: each term-bank row is a
valid spelling/reading pair. Katanki retains common kanji headwords (★, score at
least 100), omits irregular/rare/obsolete forms and kana-preferred or archaic
entries, and ranks by score, length, spelling and reading. One suggestion is shown
per spelling. Source vocabulary precedes defaults and wins duplicate matching.
The suggestion index contains 17,126 word/reading/score rows, approximately 540 KB.
The full 38.8 MB export is retained byte-for-byte, including all entries, definitions,
examples, tags, structured ruby markup, images, and metadata. Common-word filtering
only affects automatic suggestions; it does not discard the full dictionary.
The complete add-on remains under the 50 MB packaging budget.

Readings are retained as whole-word readings; furigana positions are not inferred.
The index omits definitions, sentences, audio, and positional data; these omissions
do not apply to the original archive. The derivative remains CC BY-SA 4.0. Both
the full export and index include attribution and license texts offline, including
CC BY 2.0 FR for Tatoeba sentences in the archive. See
[downloads](https://jitendex.org/pages/downloads.html) and
[source attribution](https://jitendex.org/pages/legal.html).

Enable **Discovered and default words** in the card category settings to include
Jitendex suggestions. Parts suggestions come from kanji in the current discovery
snapshot whose KanjiVG component entries contain the part. They require no word
review-status or furigana filtering. All managed suggestions are stored even when
hidden or beyond the display limit. Production ambiguity uses only the limited,
visible, masked clues. Existing notes use the refresh rules above.

Dictionary readings can help with future furigana, but whole-word readings do not
always resolve ambiguous readings or show which kana belongs to each kanji.

## Open questions

- Refining word ranking and expanding the conservative default-word coverage.
- Editable example format, optional readings, and duplicate matching rules.
- Furigana alignment and handling of ambiguous readings.
- Whether seen-only filtering excludes defaults without a matching reviewed word.
- Rich preview/editing of legacy migration and customized template upgrades.

## Verification

Creation and refresh integration verified on 2026-10-23: 238 automated tests pass;
lint and formatting pass. The offline packaged build includes the word pack,
checksums, provenance and licenses. Real Anki checks cover field/template migration,
custom-template preservation, unchanged existing scheduling, and grouped Undo.
The packaged Qt webview checks user ordering, duplicates, limits (including 0),
hidden examples, and the shared preview renderer. Host baseline: Linux Anki
26.09.3 / Python 3.14.8. `scripts/smoke_example_refresh.py` checks real source
additions/removals, manual edits, migration decisions, unchanged scheduling and
Undo. `scripts/smoke_refresh.py` exercises existing-note updates through the actual
Refresh button and CollectionOp. Furigana and seen/new filtering remain pending.

Remaining acceptance coverage for the full design:

Cover limits including 0 and more user examples than the limit, ordering,
duplicates, masking, ambiguity after limiting, Parts examples, and preview parity.

For updates, cover source additions/removals, seen-state changes, disabled refresh,
manual edits, migration, stale previews, repeated refresh, and Undo. Check that
note/card IDs, scheduling, and review history remain unchanged.
