"""On-disk cache of the last data spotipulse fetched, for an instant start.

Views show what's cached right away, then refresh from Spotify in the background.
Everything here is best effort: a missing, old or corrupt cache just means "fetch normally".
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import asdict
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

from .api import Artist, PlayedItem, PlaylistInfo, Profile, Track
from .genres import GenreCount

# Bump when the shape of cached data changes: older files are then ignored.
CACHE_VERSION = 1
MAX_COVERS = 400


def _track(d: dict[str, Any]) -> Track:
    return Track(**{**d, "artists": tuple(d["artists"])})


def _artist(d: dict[str, Any]) -> Artist:
    genres = d.get("genres")
    return Artist(**{**d, "genres": tuple(genres) if genres is not None else None})


def encode_top(tracks: list[Track], artists: list[Artist], genres: list[GenreCount]) -> dict[str, Any]:
    return {
        "tracks": [asdict(t) for t in tracks],
        "artists": [asdict(a) for a in artists],
        "genres": [asdict(g) for g in genres],
    }


def decode_top(d: dict[str, Any]) -> tuple[list[Track], list[Artist], list[GenreCount]]:
    return (
        [_track(t) for t in d["tracks"]],
        [_artist(a) for a in d["artists"]],
        [GenreCount(**g) for g in d["genres"]],
    )


def encode_profile(profile: Profile) -> dict[str, Any]:
    return asdict(profile)


def decode_profile(d: dict[str, Any]) -> Profile:
    return Profile(**{**d, "playlists": tuple(PlaylistInfo(**p) for p in d["playlists"])})


def encode_recent(items: list[PlayedItem]) -> list[dict[str, Any]]:
    return [{"track": asdict(i.track), "played_at": i.played_at.isoformat()} for i in items]


def decode_recent(d: list[dict[str, Any]]) -> list[PlayedItem]:
    return [PlayedItem(_track(i["track"]), datetime.fromisoformat(i["played_at"])) for i in d]


class DiskCache:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.covers = root / "covers"
        self._lock = threading.Lock()

    # ---------- JSON data ----------

    def _path(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def load(self, key: str) -> tuple[Any, float] | None:
        """(data, saved_at epoch seconds) or None."""
        try:
            payload = json.loads(self._path(key).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if payload.get("version") != CACHE_VERSION:
            return None
        return payload.get("data"), float(payload.get("saved_at", 0))

    def save(self, key: str, data: Any) -> None:
        payload = {"version": CACHE_VERSION, "saved_at": time.time(), "data": data}
        path = self._path(key)
        with self._lock:
            try:
                self.root.mkdir(parents=True, exist_ok=True)
                tmp = path.with_suffix(".tmp")
                tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                tmp.replace(path)
            except OSError:
                pass

    def load_decoded(self, key: str, decode) -> tuple[Any, float] | None:
        cached = self.load(key)
        if cached is None:
            return None
        try:
            return decode(cached[0]), cached[1]
        except (KeyError, TypeError, ValueError):
            return None

    # ---------- cover images ----------

    def _cover_path(self, url: str) -> Path:
        return self.covers / (hashlib.sha1(url.encode("utf-8")).hexdigest() + ".jpg")

    def load_cover(self, url: str) -> Image.Image | None:
        try:
            data = self._cover_path(url).read_bytes()
            return Image.open(BytesIO(data)).convert("RGB")
        except (OSError, ValueError):
            return None

    def save_cover(self, url: str, image: Image.Image) -> None:
        with self._lock:
            try:
                self.covers.mkdir(parents=True, exist_ok=True)
                image.convert("RGB").save(self._cover_path(url), "JPEG", quality=90)
                self._prune_covers()
            except OSError:
                pass

    def _prune_covers(self) -> None:
        files = list(self.covers.glob("*.jpg"))
        if len(files) <= MAX_COVERS:
            return
        files.sort(key=lambda f: f.stat().st_mtime)
        for old in files[: len(files) - MAX_COVERS]:
            old.unlink(missing_ok=True)
