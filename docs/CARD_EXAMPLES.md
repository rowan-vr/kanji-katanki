# Card examples

Design for Phase 3. The settings UI, including per-category example limits, is in
place. Example fields, rendering, and updates to existing cards still need
implementation.

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

The automatic-example-refresh setting controls updates to managed examples for
each category. It defaults to on. When refresh runs automatically is configured
separately.

Refresh never changes `UserExamples`. For managed fields, compare the current
value with the last generated value before updating. Leave manual edits intact
and report conflicts. Existing notes have no recorded generated values, so they
need a migration step before automatic updates can safely begin.

Updates use Anki APIs and support Undo. Preserve note/card IDs, scheduling,
review history, tags, and decks. Removing source vocabulary must never delete a
generated note.

For updates that would leave a production card without valid or distinct clues,
the suggested behavior is to keep its current clues and report a conflict. This
policy is still open.

## Default words

Jitendex is the planned source for a separate follow-up PR. Download a pinned
Yomitan export during the build and prepare an offline Katanki word pack from it;
a separate JMdict bundle is not needed. Jitendex includes JMdict data and
JmdictFurigana positioning data. Inspect an export before defining the importer,
ranking, and furigana representation. See the [downloads](https://jitendex.org/pages/downloads.html)
and [source attribution](https://jitendex.org/pages/legal.html).

Prefer common contemporary words containing the target kanji. Filter out rare or
archaic spellings and forms usually written in kana where appropriate. Respect
spelling/reading restrictions. Defaults would follow the user's vocabulary words
in the display order.

The pack would include version information, attribution, and notices, like the
existing dictionary packs. Card rendering stays offline. Dictionary readings can
help with furigana, but do not always resolve ambiguous readings or show which
kana belongs to each kanji.

## Open questions

- Jitendex export mapping, example ranking, and pack contents (follow-up PR).
- Editable example format, optional readings, and duplicate matching rules.
- Furigana alignment and handling of ambiguous readings.
- Whether seen-only filtering excludes defaults without a matching reviewed word.
- Storage of generated values and source information, and migration of existing
  notes and customized templates.
- Handling updates that would make production clues empty or ambiguous.

## Verification

Cover limits including 0 and more user examples than the limit, ordering,
duplicates, masking, ambiguity after limiting, Parts examples, and preview parity.

For updates, cover source additions/removals, seen-state changes, disabled refresh,
manual edits, migration, stale previews, repeated refresh, and Undo. Check that
note/card IDs, scheduling, and review history remain unchanged.
