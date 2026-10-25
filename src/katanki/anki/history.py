"""Read current Katanki ownership and original Anki revlog evidence."""

from ..stats.history import ReviewEvidence
from .statistics import read_progress


def read_history(collection):
    progress = read_progress(collection)
    cards = {card.card_id: card for card in progress.cards}
    if not cards:
        return (), progress.warnings
    # One streaming query avoids one backend call per card and SQL parameter limits.
    reviews = []
    for stamp, cid, rating, kind, previous in collection.db.execute(
        "select id, cid, ease, type, lastIvl from revlog order by id"
    ):
        if card := cards.get(cid):
            reviews.append(ReviewEvidence(stamp, card.character, card.mode, rating, kind, previous))
    return tuple(reviews), progress.warnings
