"""Local SQLite listening history: schema, writes, query helpers."""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from .api import Track

SCHEMA = """
CREATE TABLE IF NOT EXISTS plays (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id    TEXT    NOT NULL,
    name        TEXT    NOT NULL,
    artists     TEXT    NOT NULL,
    album       TEXT    NOT NULL,
    duration_ms INTEGER NOT NULL,
    played_at   TEXT    NOT NULL  -- ISO 8601, UTC, when the track started
);
CREATE INDEX IF NOT EXISTS idx_plays_played_at ON plays (played_at);
CREATE INDEX IF NOT EXISTS idx_plays_track ON plays (track_id, played_at);
"""

# Two sightings of the same track starting within this window are the same play
# (e.g. spotipulse restarted mid-song).
DEDUP_WINDOW = timedelta(seconds=90)


@dataclass(frozen=True)
class DayTotal:
    day: date
    plays: int
    ms: int


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat(timespec="seconds")


class HistoryDB:
    def __init__(self, path: Path | str) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def record_play(self, track: Track, started_at: datetime) -> bool:
        """Log a play. Returns False if it was already logged."""
        start = started_at if started_at.tzinfo else started_at.replace(tzinfo=UTC)
        with self._lock:
            duplicate = self._conn.execute(
                "SELECT 1 FROM plays WHERE track_id = ? AND played_at BETWEEN ? AND ? LIMIT 1",
                (track.id, _iso(start - DEDUP_WINDOW), _iso(start + DEDUP_WINDOW)),
            ).fetchone()
            if duplicate:
                return False
            self._conn.execute(
                "INSERT INTO plays (track_id, name, artists, album, duration_ms, played_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (track.id, track.name, track.artist_line, track.album, track.duration_ms, _iso(start)),
            )
            self._conn.commit()
        return True

    def play_count(self) -> int:
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM plays").fetchone()[0]

    def first_play(self) -> datetime | None:
        with self._lock:
            row = self._conn.execute("SELECT MIN(played_at) FROM plays").fetchone()
        return datetime.fromisoformat(row[0]) if row and row[0] else None

    def plays_between(self, start: datetime, end: datetime) -> list[tuple[datetime, int]]:
        """(played_at, duration_ms) for plays in [start, end), oldest first."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT played_at, duration_ms FROM plays WHERE played_at >= ? AND played_at < ? "
                "ORDER BY played_at",
                (_iso(start), _iso(end)),
            ).fetchall()
        return [(datetime.fromisoformat(p), ms) for p, ms in rows]

    def daily_totals(self, tz=None) -> list[DayTotal]:
        """Per local day totals over the whole history, oldest first."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT played_at, duration_ms FROM plays ORDER BY played_at"
            ).fetchall()
        totals: dict[date, list[int]] = {}
        for played_at, ms in rows:
            day = datetime.fromisoformat(played_at).astimezone(tz).date()
            bucket = totals.setdefault(day, [0, 0])
            bucket[0] += 1
            bucket[1] += ms
        return [DayTotal(d, p, ms) for d, (p, ms) in sorted(totals.items())]
