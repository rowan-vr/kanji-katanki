# Historical statistics

Open **History…** in the kanji statistics dashboard. The native Qt charts show
cumulative unique kanji reviewed and daily retention, with exact dates and
numerators/denominators in the table. Choose recognition/writing independently
and 90 days, 365 days, or all available history. History is read when the window
opens; reopen it after reviewing or syncing to refresh the evidence.

Days use the machine's current local timezone and midnight boundary, rather than
Anki's configurable study-day rollover. Timestamps are interpreted for each date
so local DST transitions are respected. Changing timezone can move old answers
to different calendar days.

Only current Katanki-owned kanji cards and their surviving Anki review logs are
included. Current card type/interval is never used to reconstruct past mastery.
Editing a note's Character or changing note type changes attribution; deleted
cards and deleted/truncated logs cannot be recovered. Suspension does not remove
past evidence. Primitives and vocabulary do not imply kanji knowledge.

**Kanji answered** counts unique characters answered that day (ratings 1–4,
learning/review/relearning/filtered kinds 0–3). **First observed** means the first
surviving answer of a character in that mode. **Cumulative** includes earlier
history outside the selected window and deduplicates cards for the same kanji.
These measures show observed study exposure, not acquisition or mastery.

**Retention** is a clearly defined kanji-day measure, not Anki's standard
True Retention statistic: only scheduled-review entries (kind 1) whose previous
interval is at least one day qualify. The earliest qualifying answer per
character, mode and calendar day is used; Again fails, Hard/Good/Easy pass.
Learning, relearning, filtered/cram, same-day previous intervals, manual/reset
entries, and rating-zero logs do not enter this denominator. A day with no
eligible test is missing (a chart gap), never 0%. The window summary divides total
passed kanji-days by total eligible kanji-days, not an average of percentages.

No collection, scheduling, review history, configuration, or profile files are
written. No snapshots are persisted and historical scheduling states are not
invented from the current collection.

The rating-zero, review-kind and signed-interval policy follows
[Anki's revlog definitions](https://github.com/ankitects/anki/blob/main/rslib/src/revlog/mod.rs).
