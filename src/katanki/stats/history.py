"""Historical evidence, never inferred historical scheduling or mastery."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta


@dataclass(frozen=True)
class ReviewEvidence:
    timestamp_ms: int
    character: str
    mode: str
    rating: int
    kind: int
    previous_interval: int


@dataclass(frozen=True)
class HistoryDay:
    day: date
    answered: int
    introduced: int
    cumulative: int
    retained: int
    tested: int

    @property
    def retention(self):
        return 100 * self.retained / self.tested if self.tested else None


def history_days(reviews, mode, *, start=None, end=None, timezone=None):
    """Calendar days in local timezone (or supplied tz); first eligible answer per kanji/day.

    Retention is scheduled review success with a prior interval of at least one day: kind 1 and
    previous interval >= 1 day, ratings Hard/Good/Easy pass. Learning, relearning,
    filtered/cram, manual/reset and sub-day prior intervals are excluded from retention.
    Activity/exposure includes learning/relearning and filtered answers (kinds 0–3).
    """
    events = sorted(
        (r for r in reviews if r.mode == mode and 1 <= r.rating <= 4 and r.kind in (0, 1, 2, 3)),
        key=lambda r: r.timestamp_ms,
    )
    buckets, seen, tested = {}, set(), set()
    for review in events:
        day = datetime.fromtimestamp(review.timestamp_ms / 1000, timezone).date()
        if end and day > end:
            continue
        bucket = buckets.setdefault(day, [set(), set(), 0, 0])
        bucket[0].add(review.character)
        if review.character not in seen:
            seen.add(review.character)
            bucket[1].add(review.character)
        key = (day, review.character)
        if review.kind == 1 and review.previous_interval >= 1 and key not in tested:
            tested.add(key)
            bucket[2] += review.rating > 1
            bucket[3] += 1
    if not buckets:
        return ()
    first = start or min(buckets)
    last = end or max(buckets)
    cumulative = sum(len(bucket[1]) for day, bucket in buckets.items() if day < first)
    result = []
    while first <= last:
        answered, introduced, retained, count = buckets.get(first, ((), (), 0, 0))
        cumulative += len(introduced)
        result.append(
            HistoryDay(first, len(answered), len(introduced), cumulative, retained, count)
        )
        first += timedelta(days=1)
    return tuple(result)
