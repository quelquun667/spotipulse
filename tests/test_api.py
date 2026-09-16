from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
import requests
import spotipy

from spotipulse.api import SpotifyAPI, SpotifyAPIError

TRACK = {
    "id": "t1",
    "name": "Song",
    "duration_ms": 180000,
    "artists": [{"name": "A"}, {"name": "B"}],
    "album": {
        "name": "Record",
        "images": [
            {"url": "big", "width": 640},
            {"url": "mid", "width": 300},
            {"url": "small", "width": 64},
        ],
    },
    "external_urls": {"spotify": "https://open.spotify.com/track/t1"},
}


@pytest.fixture
def client():
    return MagicMock(spec=spotipy.Spotify)


def test_now_playing_track(client):
    client.current_user_playing_track.return_value = {
        "item": TRACK,
        "progress_ms": 42000,
        "is_playing": True,
        "currently_playing_type": "track",
    }
    state = SpotifyAPI(client).now_playing()
    assert state.is_playing and state.progress_ms == 42000
    assert state.track.artists == ("A", "B")
    assert state.track.artist_line == "A, B"
    assert state.track.image_url == "mid"  # smallest image that's still >= 300px


def test_now_playing_nothing(client):
    client.current_user_playing_track.return_value = None
    assert SpotifyAPI(client).now_playing() is None
    client.current_user_playing_track.return_value = {"item": None, "is_playing": False}
    assert SpotifyAPI(client).now_playing() is None


def test_now_playing_episode(client):
    client.current_user_playing_track.return_value = {
        "item": {"id": "e1", "name": "Ep", "duration_ms": 1000, "show": {"name": "Show", "publisher": "Pub"}},
        "progress_ms": 1,
        "is_playing": False,
        "currently_playing_type": "episode",
    }
    state = SpotifyAPI(client).now_playing()
    assert state.kind == "episode"
    assert state.track.artists == ("Pub",)
    assert state.track.album == "Show"


def test_top_items_pass_time_range(client):
    client.current_user_top_tracks.return_value = {"items": [TRACK]}
    client.current_user_top_artists.return_value = {
        "items": [{"id": "a1", "name": "Artist", "genres": ["pop"], "images": []}, {"id": "a2", "name": "X"}]
    }
    api = SpotifyAPI(client)
    tracks = api.top_tracks("medium_term", limit=20)
    artists = api.top_artists("long_term", limit=50)
    client.current_user_top_tracks.assert_called_once_with(limit=20, time_range="medium_term")
    client.current_user_top_artists.assert_called_once_with(limit=50, time_range="long_term")
    assert tracks[0].name == "Song"
    assert artists[0].genres == ("pop",)
    assert artists[1].genres is None  # field absent -> unknown, not "no genres"


def test_recently_played_parses_timestamps(client):
    client.current_user_recently_played.return_value = {
        "items": [{"track": TRACK, "played_at": "2026-09-15T20:01:02.123Z"}, {"track": None}]
    }
    items = SpotifyAPI(client).recently_played()
    assert len(items) == 1
    assert items[0].played_at == datetime(2026, 9, 15, 20, 1, 2, 123000, tzinfo=UTC)


def test_single_artist_lookup(client):
    client.artist.return_value = {"id": "a1", "name": "Artist", "genres": ["house"]}
    assert SpotifyAPI(client).artist("a1").genres == ("house",)
    client.artist.assert_called_once_with("a1")


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (spotipy.SpotifyException(429, -1, "too many"), "rate limit"),
        (spotipy.SpotifyException(401, -1, "nope"), "--logout"),
        (spotipy.SpotifyException(500, -1, "boom"), "Spotify error"),
        (requests.ConnectionError(), "connection"),
    ],
)
def test_errors_become_friendly(client, error, message):
    client.current_user_top_tracks.side_effect = error
    with pytest.raises(SpotifyAPIError, match=message):
        SpotifyAPI(client).top_tracks("short_term")
