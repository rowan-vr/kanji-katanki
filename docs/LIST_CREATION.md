# Create cards from lists and groups

Open Katanki → Add new kanji cards and choose a source from the dropdown:
Manual input, an enabled list, a list group, or a personal list. Type in the
source picker to search; group names include their parent list. Targets follow
list order. Choose an amount (default **10**) or check **All**. The amount counts
kanji needing new cards after existing cards and saved ignores are checked;
recognition and production can each create a card for the same kanji. Required
parts are retained, so the number of cards can exceed the selected kanji amount.
The amount and All controls are disabled for Manual input. For lists, the text
box previews the actual new kanji after checking existing cards, saved ignores,
and the selected card types. It cannot be edited. Changing the source, amount,
or card types refreshes this preview. When nothing can be created, it shows
**No new cards** in red and disables Create.

For Parts-only creation, the amount selects the first kanji whose parts to prepare.

The dialog shows the selected characters and lets you select Recognition,
Production, and/or Parts cards. Choose **Review cards…** to prepare the existing
creation review. Dictionary loading and preparation run in the background. The
review uses your configured decks, tags, and card settings, checks existing cards
and saved ignored identities, and supports per-card choices. Cards are written
only after the review's explicit Create action. Automatic generation can remain
off. Production examples use Jitendex with the existing manual-entry fallback.

Missing dictionary entries remain unsupported targets and are reported; they are
not replaced or normalized. Compatibility ideographs retain their own identities.
Existing notes, scheduling, and review history are preserved. Parts cards are
optional components derived from the selected kanji using the existing planner.
