"""Aggregates top-artist genres into ranked counts."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

from .api import Artist


@dataclass(frozen=True)
class GenreCount:
    genre: str
    count: int
    # Sum of (N - rank) over the artists carrying the genre: favours genres of your very top artists.
    score: int


def fill_missing_genres(artists: Sequence[Artist], fetch: Callable[[str], Artist]) -> list[Artist]:
    """Fetch GET /artists/{id} for artists whose payload lacked the `genres` field.

    Top-artist payloads normally include genres already, so this is usually zero calls.
    """
    filled = []
    for artist in artists:
        if artist.genres is None:
            try:
                artist = replace(artist, genres=fetch(artist.id).genres or ())
            except Exception:
                artist = replace(artist, genres=())
        filled.append(artist)
    return filled


def top_genres(artists: Sequence[Artist], limit: int = 15) -> list[GenreCount]:
    counts: dict[str, list[int]] = {}
    total = len(artists)
    for rank, artist in enumerate(artists):
        for genre in dict.fromkeys(g.strip().lower() for g in artist.genres or () if g.strip()):
            entry = counts.setdefault(genre, [0, 0])
            entry[0] += 1
            entry[1] += total - rank
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1][0], -kv[1][1], kv[0]))
    return [GenreCount(g, c, s) for g, (c, s) in ranked[:limit]]
