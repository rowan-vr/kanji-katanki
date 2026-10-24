# Card examples

Card example design, partially implemented in Phase 3. Remaining example and
rendering work is scheduled for Phase 4 alongside the interface improvements. Creation and Refresh now store managed
suggestions in `VocabExamples` and protect `UserExamples`. Recognition and Parts
show examples on the back. Production uses a generated `Prompt` snapshot rebuilt
on Refresh, merging user examples first, deduplicating, limiting, and masking all
target occurrences. Settings control default words, visibility and limits.
Furigana, seen/new filtering and live production-front rendering after an editor
change remain pending; refresh applies user-example edits to production clues.
Exact previous stock templates are upgraded during creation or example refresh;
managed-field refresh also upgrades legacy notes without a replacement review.
Customized templates and styles are preserved.

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
eligible examples on the note. Apply visibility and limits to front clues; the
answer side shows every configured stored example, including user examples,
independently of the front limit or front-example visibility.
For long lists, show 12 chips initially and put the rest in an accessible native
**Show N more words** disclosure. Display the full unique count in the heading;
every word is stored/rendered, with no additional generator or back-display cap.

Show user examples first, followed by managed examples. Remove duplicates before
applying the front limit, keeping the user's version. Preserve user ordering and
keep managed examples in a stable order. Both fields count toward the front limit.

Recognition and Production respect the example visibility, source, furigana,
and seen/new settings. Parts has no furigana or word review-status filter.

Production masks every occurrence of the target kanji in both fields without
changing the stored text. Check for ambiguous production clues after filtering,
masking, and limiting: an example that isn't shown cannot distinguish two cards.
Previews and actual cards must render the same content.

## Review layout and word status

Recognition fronts focus on the character; production fronts show the meaning
and masked clue chips without a written instruction prompt. Backs use a separate
answer layout with the character, meaning/readings, components, stroke controls,
and all configured words. They do not repeat the question/front template.
The visual direction draws on [Kanji GOD's card structure](https://github.com/migaku-official/Migaku-Kanji-Addon/blob/main/templates/src/templates/back-recognition.njk):
a strong character focus with separate supporting sections and related words.

Vocabulary chips show a saved snapshot from the configured Discovery sources:

- **Blue:** at least one matching source card has graduated into Anki review
  (card type 2, including young/mature and suspended/buried review cards).
- **Rose with a double border:** relearning (card type 3).
- **Amber with a dashed border:** learning (card type 1).
- **Plain outlined:** new (card type 0).
- **Gray:** no matching source card exists. Default or user-only words without
  a matching configured source card also use gray.

Creation and enabled example refresh capture the status in `VocabExamples` data
attributes. Sort words **known → relearning → learning → new → no card**.
Duplicate source words/cards use the first matching state in that order.
Deduplicate user-first, retain a matching managed word's status, and preserve
user-first order within each state group. Older generic card-exists snapshots
remain outlined until refresh records their exact stage. No note/card IDs or live collection
links are embedded. The legend says these are statuses at last creation/refresh;
reviewing vocabulary changes the colors on the next enabled refresh. Related
kanji on Parts backs use neutral chips without vocabulary-status claims.

Templates, CSS, scripts, examples, status metadata, and sanitized SVGs are carried
by the note type and fields. Exported cards can be studied offline without the
add-on, source decks, or dictionaries. Responsive layouts and Anki night-mode
styles are shared by card previews and actual cards. Generate a standalone gallery
with `python scripts/preview_cards.py`.

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

Refresh never changes `UserExamples`. Enabled update options overwrite Katanki-managed
fields even when they were manually edited or tracking is missing, damaged or from
a newer version. No replacement review is required. Tracking is regenerated with
HTML-safe JSON. Duplicate owned identities, stale snapshots, unavailable data and
ambiguous production clues still prevent an unsafe update. Customized templates
are left intact, and updates support Undo without changing scheduling or history.

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

Builds include the complete Jitendex Yomitan archive. A lightweight suggestion
index is compiled in memory on first use from the pinned
2026.10.03.0 Yomitan export. The shared `bundled/SOURCES.json` records upstream
provenance; `datasets/bundled-lock.json` pins the published release pack.
Jitendex lives at `bundled/jitendex.zip` alongside the other dataset payloads.
The export was inspected before implementing conversion: each term-bank row is a
valid spelling/reading pair. Katanki retains common kanji headwords (★, score at
least 100), omits irregular/rare/obsolete forms, and retains an entry if it has
at least one modern, non-kana-preferred sense. Group-level usage tags apply to
their own senses; an archaic secondary meaning does not discard a modern common
word such as `大丈夫`. Suggestions rank by score, length, spelling and reading. One suggestion is shown
per spelling. Source vocabulary precedes defaults and wins duplicate matching.
The suggestion index contains 17,616 word/reading/score rows, approximately 541 KiB.
The full 38.8 MB export is retained byte-for-byte, including all entries, definitions,
examples, tags, structured ruby markup, images, and metadata. Common-word filtering
only affects automatic suggestions; it does not discard the full dictionary.
The complete add-on remains under the 50 MB packaging budget.

Readings are retained as whole-word readings; furigana positions are not inferred.
The in-memory index omits definitions, sentences, audio, and positional data; these omissions
do not apply to the original archive. The derivative remains CC BY-SA 4.0. Both
the full export and index include attribution and license texts offline, including
CC BY 2.0 FR for Tatoeba sentences in the archive. See
[downloads](https://jitendex.org/pages/downloads.html) and
[source attribution](https://jitendex.org/pages/legal.html).

Use **Examples on the front** and **Examples on the back** independently under
Settings → Cards → Recognition/Production. Each side offers **Words from my
selected Anki fields** or **My Anki words + Jitendex dictionary words**. The former
uses only the configured Discovery fields; the latter adds matching common
Jitendex words. Merely enabling Jitendex under Dictionaries does not add examples.
For example, if `丈夫` is the only selected expression containing `丈`, the first
option supplies only `丈夫`; dictionary additions require the second option on
the relevant side. Use Anki-only on the front and the combined choice on the back
for vocabulary-based questions with dictionary reference words on the answer.

Settings version 7 adds an independent front choice and preserves version-1–6
shared choices on both sides. Internally, the original `example_source` setting
now selects the back, and `front_example_source` can override it for the front.
Store the union of selected words with `data-front` / `data-back` flags in
`VocabExamples`; the note field schema and protected baseline shape stay unchanged.
Recognition renders only front-eligible words with the configured visibility/limit.
Production creation and refresh build their masked `Prompt` only from front-eligible
words, including user examples first. Back-only words never disambiguate a front.
Dictionary-data-only refresh retains the saved front flags instead of introducing
hidden back words into a question. Back rendering filters on back flags and still
provides every selected back word through expansion. Unmarked older words remain
available on both sides until the next enabled refresh. Per-note flags and front
snapshots keep exported cards independent of the add-on or selected source decks.

The Dictionaries tab chooses the bundled/installed version, a local Yomitan ZIP,
or Disabled. Generation and Refresh use that selection; disabling Jitendex keeps
Anki words. Compatible dictionary updates use the shared dataset update sequence.
Suggestion cache format 2 rebuilds indexes from the previous
entry-wide sense-filter policy automatically, retaining the original archive.

Parts suggestions come from kanji in the current discovery
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

Layout verification, 2026-10-24: `scripts/smoke_card_layout.py` creates real cards,
exports only the generated notes, imports into a clean collection without source
vocabulary, and renders the imported front/back templates in an offline Qt
webview without an add-on bridge. It checks all five saved word statuses and their
order/distinct chip styles, independent Anki-only fronts and dictionary-expanded
backs, UI control save/reopen, user-first deduplication within groups, all 16 words
despite a front limit of one, expansion beyond 12 chips, production masking, stroke-number
toggle/playback, light/dark themes, and 360/900 px layouts. Native AnkiMobile and
AnkiDroid verification remains pending. Unit coverage includes status aggregation,
stage changes on refresh, stock-layout upgrades, and customized-layout preservation.
All 377 unit tests, lint/format checks, the existing real-Anki generation and
example-refresh lifecycle checks, and the offline add-on build pass.
The Qt check also reproduces old JSON corruption through an HTML editor round
trip and verifies the escaped record survives unchanged. Real-Anki checks cover
automatic replacement of damaged tracking and manually edited managed fields,
unchanged user examples/tags/
scheduling/history, grouped Undo, and duplicate-free repeated refresh. The native
review lifecycle also verifies a new tracking record remains readable after answering.

Cover limits including 0 and more user examples than the limit, ordering,
duplicates, masking, ambiguity after limiting, Parts examples, and preview parity.

For updates, cover source additions/removals, seen-state changes, disabled refresh,
manual edits, migration, stale previews, repeated refresh, and Undo. Check that
note/card IDs, scheduling, and review history remain unchanged.
