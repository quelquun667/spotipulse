from datetime import date, timedelta

from spotipulse.db import DayTotal
from spotipulse.stats import (
    compare_periods,
    current_streak,
    daily_series,
    format_change,
    format_clock,
    format_duration,
    longest_streak,
    rank_changes,
    total_runtime_ms,
)

from conftest import make_track

TODAY = date(2026, 9, 16)


def day(offset: int, ms: int = 60_000, plays: int = 1) -> DayTotal:
    return DayTotal(TODAY - timedelta(days=offset), plays, ms)


def test_format_duration():
    assert format_duration(0) == "0m"
    assert format_duration(45 * 60_000) == "45m"
    assert format_duration(3 * 3_600_000 + 5 * 60_000) == "3h 05m"


def test_format_clock():
    assert format_clock(225_000) == "3:45"
    assert format_clock(3_725_000) == "1:02:05"


def test_total_runtime():
    assert total_runtime_ms([make_track(1, 1000), make_track(2, 2500)]) == 3500


def test_current_streak_counts_back_from_today_or_yesterday():
    assert current_streak([TODAY, TODAY - timedelta(days=1), TODAY - timedelta(days=2)], TODAY) == 3
    # nothing yet today, but yesterday continues the streak
    assert current_streak([TODAY - timedelta(days=1), TODAY - timedelta(days=2)], TODAY) == 2
    assert current_streak([TODAY - timedelta(days=3)], TODAY) == 0
    assert current_streak([], TODAY) == 0


def test_longest_streak():
    days = [TODAY - timedelta(days=d) for d in (0, 1, 5, 6, 7, 8, 20)]
    assert longest_streak(days) == 4
    assert longest_streak([]) == 0


def test_daily_series_fills_gaps():
    series = daily_series([day(0, 10), day(2, 30)], 4, TODAY)
    assert [d.ms for d in series] == [0, 30, 0, 10]
    assert series[-1].day == TODAY


def test_compare_periods():
    days = [day(0, 100), day(6, 100), day(7, 50), day(13, 50), day(14, 999)]
    c = compare_periods(days, TODAY, 7, "Last 7 days")
    assert (c.current_ms, c.previous_ms) == (200, 100)
    assert c.change_pct == 100
    assert format_change(c.change_pct) == "▲ 100%"


def test_compare_periods_without_previous_data():
    c = compare_periods([day(0)], TODAY, 7, "Last 7 days")
    assert c.change_pct is None
    assert format_change(None) == "—"


def test_rank_changes():
    changes = rank_changes(["a", "b", "c", "d"], ["b", "a", "x", "d"])
    assert changes == {"a": 1, "b": -1, "c": None, "d": 0}
