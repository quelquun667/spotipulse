"""`spotipulse --demo`: the whole dashboard on made-up data, no Spotify account or app needed.

Every artist, track, album and playlist here is fictional. Covers are generated.
"""

from __future__ import annotations

import colorsys
import random
import time
from datetime import UTC, datetime, timedelta
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter

from .api import Artist, NowPlaying, PlayedItem, PlaylistInfo, Profile, Track
from .db import HistoryDB

ARTISTS: list[tuple[str, tuple[str, ...]]] = [
    ("Velvet Static", ("indie pop", "dream pop")),
    ("Nora Sol", ("alt r&b", "neo soul")),
    ("Midnight Arcade", ("synthwave", "electronic")),
    ("Kairo", ("french rap", "trap")),
    ("Coastline Echo", ("indie rock", "surf rock")),
    ("Juno Park", ("bedroom pop", "indie pop")),
    ("Ash & Ember", ("folk", "indie folk")),
    ("Solenne", ("french pop", "chanson")),
    ("Blue Tangent", ("house", "deep house")),
    ("Mira Lane", ("pop", "dance pop")),
    ("Low Orbit", ("lo-fi", "chillhop")),
    ("Paper Lanterns", ("indie pop", "folk pop")),
]

TRACKS: list[tuple[str, int, str, int]] = [  # title, artist index, album, seconds
    ("Glass Hearts", 0, "Soft Focus", 214),
    ("Afterglow Drive", 2, "Neon Tapes", 247),
    ("Rue des Lilas", 7, "Été Indien", 198),
    ("Satellite Summer", 5, "Posters on the Ceiling", 176),
    ("Slow Burn", 1, "Honey & Static", 231),
    ("Minuit Pile", 3, "Béton Doux", 189),
    ("Low Tide", 4, "Salt Water Radio", 205),
    ("Paper Satellites", 11, "Small Lights", 222),
    ("Chrome Skyline", 2, "Neon Tapes", 263),
    ("Wildflower Road", 6, "Kindling", 241),
    ("Deep Blue Hour", 8, "After Hours Club", 318),
    ("Say It Twice", 9, "Mirrorball Season", 187),
    ("Tape Hiss Lullaby", 10, "Rainy Loops Vol. 2", 142),
    ("Honeycomb", 1, "Honey & Static", 204),
    ("Cassette Heart", 0, "Soft Focus", 196),
    ("Bitume", 3, "Béton Doux", 173),
    ("Golden Hour Club", 8, "After Hours Club", 295),
    ("Postcards", 5, "Posters on the Ceiling", 168),
    ("Tidal", 4, "Salt Water Radio", 233),
    ("Lanterns", 11, "Small Lights", 209),
    ("Ember Song", 6, "Kindling", 257),
    ("Dernier Métro", 7, "Été Indien", 211),
    ("Loop 04", 10, "Rainy Loops Vol. 2", 131),
    ("Disco Lights", 9, "Mirrorball Season", 199),
    ("Night Drive FM", 2, "Neon Tapes", 244),
]

PLAYLISTS = [
    ("Late Night Drive", 64),
    ("Sunday Coffee", 41),
    ("Rap FR du moment", 88),
    ("Focus Loops", 120),
    ("Summer '26", 57),
    ("Gym Hype", 73),
    ("Chill Indie", 95),
]

GENRES_ORDER = {"short_term": 0, "medium_term": 1, "long_term": 2}


@lru_cache(maxsize=64)
def cover(seed: int) -> Image.Image:
    """A generated album cover: a soft two-color gradient with a few shapes."""
    rng = random.Random(seed)
    size = 300
    hue = rng.random()
    first = tuple(int(c * 255) for c in colorsys.hsv_to_rgb(hue, 0.65, 0.9))
    second = tuple(int(c * 255) for c in colorsys.hsv_to_rgb((hue + 0.12) % 1, 0.75, 0.45))
    mask = Image.linear_gradient("L").resize((size, size)).rotate(rng.choice((0, 45, 90, 135)))
    image = Image.composite(
        Image.new("RGB", (size, size), second), Image.new("RGB", (size, size), first), mask
    )
    draw = ImageDraw.Draw(image)
    for _ in range(3):
        r = rng.randint(30, 110)
        x, y = rng.randint(0, size), rng.randint(0, size)
        light = tuple(min(255, c + 60) for c in first)
        if rng.random() < 0.5:
            draw.ellipse((x - r, y - r, x + r, y + r), outline=light, width=6)
        else:
            draw.rectangle((x - r, y - r, x + r, y + r), outline=light, width=6)
    return image.filter(ImageFilter.GaussianBlur(0.6))


def _track(index: int) -> Track:
    title, artist, album, seconds = TRACKS[index]
    return Track(
        id=f"demo-track-{index}",
        name=title,
        artists=(ARTISTS[artist][0],),
        album=album,
        duration_ms=seconds * 1000,
        image_url=f"demo://cover/{album}",
        year=str(2019 + (index * 7) % 8),
    )


def _artist(index: int) -> Artist:
    name, genres = ARTISTS[index]
    return Artist(id=f"demo-artist-{index}", name=name, genres=genres, image_url=f"demo://artist/{index}")


def _ranking(time_range: str, count: int) -> list[int]:
    """A stable, different order per period, so the Trend column has something to show."""
    order = list(range(count))
    random.Random(GENRES_ORDER[time_range] * 7 + 3).shuffle(order)
    # keep a few favorites near the top across periods
    for favorite in (0, 4, 2):
        order.remove(favorite)
        order.insert(GENRES_ORDER[time_range], favorite)
    return order


class DemoAPI:
    """Same interface as SpotifyAPI, answering from the made-up library above."""

    def __init__(self) -> None:
        self._started = time.monotonic()

    # ---------- now playing ----------

    def now_playing(self) -> NowPlaying | None:
        elapsed = time.monotonic() - self._started + 95  # start mid-song
        index = 0
        while True:
            seconds = TRACKS[index % len(TRACKS)][3]
            if elapsed < seconds:
                break
            elapsed -= seconds
            index += 1
        return NowPlaying(
            track=_track(index % len(TRACKS)),
            progress_ms=int(elapsed * 1000),
            is_playing=True,
            device_name="Living Room PC",
            device_type="computer",
            volume=64,
            shuffle=True,
            repeat="context",
            context_type="playlist",
            context_uri="demo:playlist:late-night-drive",
        )

    def queue(self, limit: int = 5) -> list[Track]:
        current = self.now_playing()
        start = int(current.track.id.rsplit("-", 1)[1]) + 1 if current else 0
        return [_track((start + i) % len(TRACKS)) for i in range(limit)]

    def context_name(self, context_type: str | None, uri: str | None) -> str | None:
        return "Late Night Drive" if uri else None

    # ---------- tops ----------

    def top_tracks(self, time_range: str, limit: int = 20) -> list[Track]:
        return [_track(i) for i in _ranking(time_range, len(TRACKS))][:limit]

    def top_artists(self, time_range: str, limit: int = 20) -> list[Artist]:
        return [_artist(i) for i in _ranking(time_range, len(ARTISTS))][:limit]

    def artist(self, artist_id: str) -> Artist:
        return _artist(int(artist_id.rsplit("-", 1)[1]))

    # ---------- history & profile ----------

    def recently_played(self, limit: int = 50) -> list[PlayedItem]:
        now = datetime.now(UTC)
        rng = random.Random(11)
        items, moment = [], now - timedelta(minutes=4)
        for i in range(limit):
            track = _track(rng.randrange(len(TRACKS)))
            items.append(PlayedItem(track, moment))
            moment -= timedelta(
                seconds=track.duration_ms // 1000 + (rng.randint(600, 7200) if i % 6 == 5 else 5)
            )
        return items

    def me_brief(self) -> tuple[str | None, str | None]:
        return "Demo Listener", "demo://avatar"

    def profile(self) -> Profile:
        return Profile(
            display_name="Demo Listener",
            user_id="demo",
            image_url="demo://avatar",
            url="https://open.spotify.com/",
            liked_tracks=1_482,
            saved_albums=37,
            followed_artists=64,
            playlist_count=len(PLAYLISTS),
            playlists=tuple(PlaylistInfo(name, tracks, "Demo Listener") for name, tracks in PLAYLISTS),
        )

    def image(self, url: str | None) -> Image.Image | None:
        if not url:
            return None
        return cover(sum(ord(c) * (i + 1) for i, c in enumerate(url)))


def demo_history() -> HistoryDB:
    """Six weeks of made-up plays, so History, streaks and listening time have something to show."""
    db = HistoryDB(":memory:")
    rng = random.Random(5)
    now = datetime.now(UTC)
    for day in range(42):
        if day in (9, 10, 23):  # a few days off, so streaks look real
            continue
        plays = rng.randint(4, 22) if day % 7 not in (5, 6) else rng.randint(12, 34)
        moment = now - timedelta(days=day, hours=rng.randint(0, 3))
        for _ in range(plays):
            track = _track(rng.randrange(len(TRACKS)))
            db.record_play(track, moment)
            moment -= timedelta(seconds=track.duration_ms // 1000 + rng.randint(5, 900))
    return db
