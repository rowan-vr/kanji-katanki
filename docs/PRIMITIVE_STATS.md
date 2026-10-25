# Parts statistics

Open **Katanki → Parts statistics** for a native, read-only snapshot. Recognition
and writing are separate modes and never contribute to kanji mastery. Search
matches graphical labels and complete component identities. State counts cover the
whole component scope; the table shows matching results, note counts, and card counts.
Refresh explicitly after editing or reviewing cards.

The scope is the union of owned Parts notes and KanjiVG component entries extracted
from kanji in all enabled target lists (including personal lists). Lists provide
source kanji, not primitive classifications. Only actual provider component entries
become targets. Disabled/unavailable stroke sources produce no invented targets;
own notes remain visible, with source failures reported in the window.

Identity follows the existing generation contract: NFC Component field content,
including multi-character graphical IDs, is preserved without compatibility folding.
Only note models marked primitive-recognition or primitive-production count.
Names, tags, decks, vocabulary, and matching Character fields are not evidence.
Missing fields and malformed component keys are excluded with warnings.

Card type determines new, learning, review (young below 21 days, mature otherwise),
or relearning. Suspended and buried cards retain their underlying learning state.
Duplicates aggregate conservatively: relearning, new, learning, young, then mature.
Missing means no supported card, and includes notes with no cards; the Notes column
makes this distinct from an absent note. Unsupported card types are excluded and
reported. Collection scheduling, notes, and review history are never changed.
