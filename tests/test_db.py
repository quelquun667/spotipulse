from datetime import UTC, datetime, timedelta

from spotipulse.db import HistoryDB

from conftest import make_track


def test_record_and_count(tmp_path):
    db = HistoryDB(tmp_path / "history.db")
    start = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    assert db.record_play(make_track(1), start)
    assert db.record_play(make_track(2), start + timedelta(minutes=4))
    assert db.play_count() == 2
    assert db.first_play() == start
    db.close()


def test_same_play_seen_twice_is_deduplicated():
    db = HistoryDB(":memory:")
    start = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    assert db.record_play(make_track(1), start)
    # restarted mid-song: the estimated start drifts by a few seconds
    assert not db.record_play(make_track(1), start + timedelta(seconds=4))
    # same song played again later is a new play
    assert db.record_play(make_track(1), start + timedelta(minutes=10))
    assert db.play_count() == 2


def test_daily_totals_group_by_day():
    db = HistoryDB(":memory:")
    base = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    db.record_play(make_track(1, 100_000), base)
    db.record_play(make_track(2, 200_000), base + timedelta(minutes=5))
    db.record_play(make_track(3, 300_000), base + timedelta(days=1))
    totals = db.daily_totals(tz=UTC)
    assert [(t.day.isoformat(), t.plays, t.ms) for t in totals] == [
        ("2026-09-01", 2, 300_000),
        ("2026-09-02", 1, 300_000),
    ]


def test_plays_between_is_half_open():
    db = HistoryDB(":memory:")
    base = datetime(2026, 9, 1, tzinfo=UTC)
    db.record_play(make_track(1), base)
    db.record_play(make_track(2), base + timedelta(days=1))
    assert len(db.plays_between(base, base + timedelta(days=1))) == 1


def test_naive_datetimes_are_treated_as_utc():
    db = HistoryDB(":memory:")
    db.record_play(make_track(1), datetime(2026, 9, 1, 12, 0))
    assert db.first_play() == datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
