from datetime import UTC, date, datetime, timedelta, timezone
from types import SimpleNamespace

from katanki.anki.history import read_history
from katanki.stats.history import ReviewEvidence, history_days


def review(day, character="日", mode="recognition", rating=3, kind=1, previous=5, hour=12):
    stamp = int(datetime(2026, 1, day, hour, tzinfo=UTC).timestamp() * 1000)
    return ReviewEvidence(stamp, character, mode, rating, kind, previous)


def test_deduplication_first_eligible_answer_and_independent_modes():
    events = [
        review(1, rating=1),
        review(1, rating=4, hour=13),
        review(1, character="月", kind=0),
        review(1, character="月", rating=2, hour=14),
        review(1, mode="writing"),
        review(2),
    ]
    rows = history_days(reversed(events), "recognition", timezone=UTC)
    assert (rows[0].answered, rows[0].introduced, rows[0].cumulative) == (2, 2, 2)
    assert (rows[0].retained, rows[0].tested, rows[0].retention) == (1, 2, 50)
    assert (rows[1].introduced, rows[1].cumulative, rows[1].retention) == (0, 2, 100)
    assert history_days(events, "writing", timezone=UTC)[0].cumulative == 1


def test_manual_entries_and_non_review_answers_are_not_retention():
    events = [
        review(1, rating=0),
        review(1, kind=4),
        review(1, kind=5),
        review(2, kind=0),
        review(2, kind=2),
        review(2, kind=3),
        review(2, previous=-600),
        review(2, previous=0),
    ]
    rows = history_days(events, "recognition", timezone=UTC)
    assert len(rows) == 1 and rows[0].day == date(2026, 1, 2)
    assert rows[0].answered == 1 and rows[0].tested == 0
    assert rows[0].retention is None


def test_window_carries_prior_exposure_and_fills_empty_days():
    rows = history_days(
        [review(1), review(4, character="月"), review(8, character="火")],
        "recognition",
        start=date(2026, 1, 3),
        end=date(2026, 1, 5),
        timezone=UTC,
    )
    assert [row.cumulative for row in rows] == [1, 2, 2]
    assert [row.answered for row in rows] == [0, 1, 0]
    assert rows[0].retention is None
    assert not history_days([], "recognition", timezone=UTC)


def test_local_calendar_midnight_uses_supplied_timezone():
    event = review(1, hour=23)
    assert history_days([event], "recognition", timezone=UTC)[0].day == date(2026, 1, 1)
    japan = timezone(timedelta(hours=9))
    assert history_days([event], "recognition", timezone=japan)[0].day == date(2026, 1, 2)


def test_current_ownership_and_original_review_rows(monkeypatch):
    import katanki.anki.history as module

    monkeypatch.setattr(
        module,
        "read_progress",
        lambda col: SimpleNamespace(
            cards=(SimpleNamespace(card_id=7, character="日", mode="recognition"),),
            warnings=("Fixture warning",),
        ),
    )
    collection = SimpleNamespace(
        db=SimpleNamespace(
            execute=lambda query: iter(
                [
                    (1000, 7, 3, 1, 5),
                    (2000, 8, 3, 1, 5),  # deleted/unowned cards excluded
                ]
            )
        )
    )
    events, warnings = read_history(collection)
    assert events == (ReviewEvidence(1000, "日", "recognition", 3, 1, 5),)
    assert warnings == ("Fixture warning",)


def test_daylight_saving_uses_historical_offset_per_event():
    from zoneinfo import ZoneInfo

    # New York switches from UTC-5 to UTC-4 on March 8, 2026.
    stamps = [datetime(2026, 3, day, 4, 30, tzinfo=UTC) for day in (8, 9)]
    events = [
        ReviewEvidence(int(stamp.timestamp() * 1000), "日", "recognition", 3, 1, 5)
        for stamp in stamps
    ]
    rows = history_days(events, "recognition", timezone=ZoneInfo("America/New_York"))
    assert [row.day for row in rows if row.answered] == [date(2026, 3, 7), date(2026, 3, 9)]
    assert rows[1].answered == 0
