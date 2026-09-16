"""Listening-time estimates, streaks and period comparisons."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from .api import Track
from .db import DayTotal


def format_duration(ms: int) -> str:
    """12_345_678 -> '3h 25m'; short values stay readable ('4m', '0m')."""
    minutes = max(0, round(ms / 60_000))
    hours, minutes = divmod(minutes, 60)
    if hours >= 24 * 10:
        return f"{hours}h"
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m"


def format_clock(ms: int) -> str:
    """Track position style: 225000 -> '3:45'."""
    seconds = max(0, ms // 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"


def total_runtime_ms(tracks: Iterable[Track]) -> int:
    return sum(t.duration_ms for t in tracks)


def listened_ms(days: Sequence[DayTotal], start: date, end: date) -> tuple[int, int]:
    """(ms, plays) for local days in [start, end]."""
    ms = plays = 0
    for d in days:
        if start <= d.day <= end:
            ms += d.ms
            plays += d.plays
    return ms, plays


def daily_series(days: Sequence[DayTotal], length: int, today: date) -> list[DayTotal]:
    """The last `length` days ending today, with empty days filled in."""
    by_day = {d.day: d for d in days}
    series = []
    for offset in range(length - 1, -1, -1):
        day = today - timedelta(days=offset)
        series.append(by_day.get(day, DayTotal(day, 0, 0)))
    return series


def current_streak(active_days: Iterable[date], today: date) -> int:
    """Consecutive listening days ending today (or yesterday, if today hasn't started yet)."""
    days = set(active_days)
    cursor = today if today in days else today - timedelta(days=1)
    streak = 0
    while cursor in days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def longest_streak(active_days: Iterable[date]) -> int:
    days = sorted(set(active_days))
    best = run = 0
    previous: date | None = None
    for day in days:
        run = run + 1 if previous and day - previous == timedelta(days=1) else 1
        best = max(best, run)
        previous = day
    return best


@dataclass(frozen=True)
class Comparison:
    label: str
    current_ms: int
    current_plays: int
    previous_ms: int
    previous_plays: int

    @property
    def change_pct(self) -> float | None:
        if self.previous_ms == 0:
            return None
        return (self.current_ms - self.previous_ms) / self.previous_ms * 100


def compare_periods(days: Sequence[DayTotal], today: date, length: int, label: str) -> Comparison:
    """The last `length` days (including today) vs. the `length` days before that."""
    current_start = today - timedelta(days=length - 1)
    previous_end = current_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=length - 1)
    cur_ms, cur_plays = listened_ms(days, current_start, today)
    prev_ms, prev_plays = listened_ms(days, previous_start, previous_end)
    return Comparison(label, cur_ms, cur_plays, prev_ms, prev_plays)


def format_change(pct: float | None) -> str:
    if pct is None:
        return "—"
    arrow = "▲" if pct > 0 else "▼" if pct < 0 else "="
    return f"{arrow} {abs(pct):.0f}%"


def rank_changes(current: Sequence[str], reference: Sequence[str]) -> dict[str, int | None]:
    """How many places each id climbed compared with a reference ranking.

    Positive = higher now than in the reference, 0 = same place, None = not in the reference (new).
    """
    previous = {item_id: rank for rank, item_id in enumerate(reference)}
    return {
        item_id: (previous[item_id] - rank if item_id in previous else None)
        for rank, item_id in enumerate(current)
    }
