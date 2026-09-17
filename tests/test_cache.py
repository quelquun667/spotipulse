import json
from datetime import UTC, datetime

from PIL import Image

from spotipulse.api import PlayedItem, PlaylistInfo, Profile
from spotipulse.cache import (
    DiskCache,
    decode_profile,
    decode_recent,
    decode_top,
    encode_profile,
    encode_recent,
    encode_top,
)
from spotipulse.genres import top_genres

from conftest import make_artist, make_track


def test_top_roundtrip(tmp_path):
    cache = DiskCache(tmp_path)
    tracks = [make_track(i) for i in range(3)]
    artists = [make_artist(0, ("pop",)), make_artist(1, None)]
    cache.save("top_short_term", encode_top(tracks, artists, top_genres(artists)))
    (got_tracks, got_artists, got_genres), saved_at = cache.load_decoded("top_short_term", decode_top)
    assert got_tracks == tracks
    assert got_artists == artists  # None genres stay None, tuples stay tuples
    assert [g.genre for g in got_genres] == ["pop"]
    assert saved_at > 0


def test_profile_and_recent_roundtrip(tmp_path):
    cache = DiskCache(tmp_path)
    profile = Profile("Noah", "noah", "img", "url", 1, 2, 3, 4, (PlaylistInfo("Chill", 30, "Noah"),))
    cache.save("profile", encode_profile(profile))
    assert cache.load_decoded("profile", decode_profile)[0] == profile

    played = [PlayedItem(make_track(1), datetime(2026, 9, 1, 12, tzinfo=UTC))]
    cache.save("recent", encode_recent(played))
    assert cache.load_decoded("recent", decode_recent)[0] == played


def test_missing_corrupt_or_outdated_cache_is_ignored(tmp_path):
    cache = DiskCache(tmp_path)
    assert cache.load("nope") is None
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    assert cache.load("broken") is None
    (tmp_path / "old.json").write_text(json.dumps({"version": 0, "data": {}}), encoding="utf-8")
    assert cache.load("old") is None
    (tmp_path / "wrong.json").write_text(json.dumps({"version": 1, "data": {"x": 1}}), encoding="utf-8")
    assert cache.load_decoded("wrong", decode_top) is None


def test_covers_are_stored_on_disk(tmp_path):
    cache = DiskCache(tmp_path)
    assert cache.load_cover("https://i.scdn.co/image/abc") is None
    cache.save_cover("https://i.scdn.co/image/abc", Image.new("RGB", (20, 20), (255, 0, 0)))
    image = cache.load_cover("https://i.scdn.co/image/abc")
    assert image is not None and image.size == (20, 20)


def test_api_uses_disk_covers_before_downloading(tmp_path, monkeypatch):
    from unittest.mock import MagicMock

    import spotipulse.api as api_module
    from spotipulse.api import SpotifyAPI

    cache = DiskCache(tmp_path)
    cache.save_cover("u", Image.new("RGB", (8, 8)))
    monkeypatch.setattr(api_module.requests, "get", MagicMock(side_effect=AssertionError("no network")))
    assert SpotifyAPI(MagicMock(), disk=cache).image("u") is not None
