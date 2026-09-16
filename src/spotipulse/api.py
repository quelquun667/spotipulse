"""Thin wrapper over the spotipy calls used by the app."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from io import BytesIO
from typing import Any

import requests
import spotipy
from PIL import Image

# Spotify only exposes these three windows for top items.
TIME_RANGES: dict[str, str] = {
    "short_term": "4 Weeks",
    "medium_term": "6 Months",
    "long_term": "1 Year",
}
PERIOD_DAYS: dict[str, int] = {"short_term": 28, "medium_term": 182, "long_term": 365}


@dataclass(frozen=True)
class Track:
    id: str
    name: str
    artists: tuple[str, ...]
    album: str
    duration_ms: int
    image_url: str | None = None
    url: str | None = None

    @property
    def artist_line(self) -> str:
        return ", ".join(self.artists)


@dataclass(frozen=True)
class Artist:
    id: str
    name: str
    # None means the payload didn't carry the field at all (vs. an artist with no genres).
    genres: tuple[str, ...] | None
    image_url: str | None = None
    url: str | None = None


@dataclass(frozen=True)
class NowPlaying:
    track: Track
    progress_ms: int
    is_playing: bool
    kind: str = "track"


@dataclass(frozen=True)
class PlayedItem:
    track: Track
    played_at: datetime


class SpotifyAPIError(Exception):
    """Any failure talking to Spotify, with a message fit for the UI."""


def _best_image(images: list[dict[str, Any]] | None, target: int = 300) -> str | None:
    """Pick the smallest image that is still at least `target` px wide."""
    if not images:
        return None
    sized = sorted(images, key=lambda i: i.get("width") or 0)
    for image in sized:
        if (image.get("width") or 0) >= target:
            return image.get("url")
    return sized[-1].get("url")


def parse_track(item: dict[str, Any]) -> Track:
    album = item.get("album") or {}
    return Track(
        id=item.get("id") or item.get("uri") or item.get("name", ""),
        name=item.get("name") or "Unknown",
        artists=tuple(a.get("name", "") for a in item.get("artists") or []) or ("Unknown",),
        album=album.get("name") or "",
        duration_ms=int(item.get("duration_ms") or 0),
        image_url=_best_image(album.get("images")),
        url=(item.get("external_urls") or {}).get("spotify"),
    )


def parse_episode(item: dict[str, Any]) -> Track:
    show = item.get("show") or {}
    return Track(
        id=item.get("id") or item.get("uri") or item.get("name", ""),
        name=item.get("name") or "Unknown episode",
        artists=(show.get("publisher") or show.get("name") or "Podcast",),
        album=show.get("name") or "",
        duration_ms=int(item.get("duration_ms") or 0),
        image_url=_best_image(item.get("images") or show.get("images")),
        url=(item.get("external_urls") or {}).get("spotify"),
    )


def parse_artist(item: dict[str, Any]) -> Artist:
    genres = item.get("genres")
    return Artist(
        id=item.get("id") or item.get("name", ""),
        name=item.get("name") or "Unknown",
        genres=tuple(genres) if genres is not None else None,
        image_url=_best_image(item.get("images")),
        url=(item.get("external_urls") or {}).get("spotify"),
    )


def parse_played_at(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass
class SpotifyAPI:
    client: spotipy.Spotify
    _image_cache: dict[str, Image.Image] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @classmethod
    def from_oauth(cls, auth_manager: spotipy.oauth2.SpotifyOAuth) -> SpotifyAPI:
        return cls(spotipy.Spotify(auth_manager=auth_manager, requests_timeout=10, retries=2))

    def _call(self, fn, *args, **kwargs) -> Any:
        try:
            return fn(*args, **kwargs)
        except spotipy.SpotifyException as exc:
            if exc.http_status == 429:
                raise SpotifyAPIError("Spotify rate limit hit — try again in a moment.") from exc
            if exc.http_status in (401, 403):
                raise SpotifyAPIError(
                    "Spotify refused the request. Try `spotipulse --logout` and sign in again."
                ) from exc
            raise SpotifyAPIError(f"Spotify error: {exc.msg}") from exc
        except spotipy.oauth2.SpotifyOauthError as exc:
            raise SpotifyAPIError(
                "Your Spotify session expired. Restart spotipulse to sign in again."
            ) from exc
        except requests.RequestException as exc:
            raise SpotifyAPIError("Can't reach Spotify — check your connection.") from exc

    def now_playing(self) -> NowPlaying | None:
        data = self._call(self.client.current_user_playing_track, additional_types=("track", "episode"))
        if not data or not data.get("item"):
            return None
        item = data["item"]
        kind = data.get("currently_playing_type") or item.get("type") or "track"
        track = parse_episode(item) if kind == "episode" else parse_track(item)
        return NowPlaying(
            track=track,
            progress_ms=int(data.get("progress_ms") or 0),
            is_playing=bool(data.get("is_playing")),
            kind=kind,
        )

    def top_tracks(self, time_range: str, limit: int = 20) -> list[Track]:
        data = self._call(self.client.current_user_top_tracks, limit=limit, time_range=time_range)
        return [parse_track(i) for i in (data or {}).get("items", []) if i]

    def top_artists(self, time_range: str, limit: int = 20) -> list[Artist]:
        data = self._call(self.client.current_user_top_artists, limit=limit, time_range=time_range)
        return [parse_artist(i) for i in (data or {}).get("items", []) if i]

    def artist(self, artist_id: str) -> Artist:
        # GET /artists/{id} — the bulk GET /artists endpoint was removed in Feb 2026.
        return parse_artist(self._call(self.client.artist, artist_id))

    def recently_played(self, limit: int = 50) -> list[PlayedItem]:
        data = self._call(self.client.current_user_recently_played, limit=limit)
        items = []
        for entry in (data or {}).get("items", []):
            if entry and entry.get("track") and entry.get("played_at"):
                items.append(PlayedItem(parse_track(entry["track"]), parse_played_at(entry["played_at"])))
        return items

    def image(self, url: str | None) -> Image.Image | None:
        """Download (and memoize) a cover/avatar image. Returns None on any failure."""
        if not url:
            return None
        with self._lock:
            cached = self._image_cache.get(url)
        if cached is not None:
            return cached
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            image = Image.open(BytesIO(response.content)).convert("RGB")
        except (requests.RequestException, OSError):
            return None
        with self._lock:
            if len(self._image_cache) > 200:
                self._image_cache.clear()
            self._image_cache[url] = image
        return image
