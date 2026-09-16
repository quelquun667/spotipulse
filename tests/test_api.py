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
        "release_date": "2019-05-03",
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
    client.current_playback.return_value = {
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
    assert state.track.year == "2019"


def test_now_playing_playback_details(client):
    client.current_playback.return_value = {
        "item": TRACK,
        "progress_ms": 1,
        "is_playing": True,
        "device": {"name": "Noah-PC", "type": "Computer", "volume_percent": 65},
        "shuffle_state": True,
        "repeat_state": "context",
        "context": {"type": "playlist", "uri": "spotify:playlist:abc"},
    }
    state = SpotifyAPI(client).now_playing()
    client.current_playback.assert_called_once_with(additional_types="track,episode")
    assert (state.device_name, state.device_type, state.volume) == ("Noah-PC", "Computer", 65)
    assert state.shuffle and state.repeat == "context"
    assert (state.context_type, state.context_uri) == ("playlist", "spotify:playlist:abc")


def test_queue_mixes_tracks_and_episodes(client):
    episode = {"type": "episode", "id": "e1", "name": "Ep", "duration_ms": 5, "show": {"name": "Show"}}
    client.queue.return_value = {"queue": [dict(TRACK, type="track"), episode] * 4}
    queue = SpotifyAPI(client).queue(limit=3)
    assert [t.name for t in queue] == ["Song", "Ep", "Song"]


def test_context_name_is_resolved_once_and_cached(client):
    client.playlist.return_value = {"name": "Chill Vibes"}
    api = SpotifyAPI(client)
    assert api.context_name("playlist", "spotify:playlist:abc") == "Chill Vibes"
    assert api.context_name("playlist", "spotify:playlist:abc") == "Chill Vibes"
    client.playlist.assert_called_once_with("abc", fields="name")
    assert api.context_name("collection", "spotify:user:me:collection") == "Liked Songs"
    assert api.context_name(None, None) is None


def test_context_name_survives_editorial_playlists(client):
    client.playlist.side_effect = spotipy.SpotifyException(404, -1, "not found")
    assert SpotifyAPI(client).context_name("playlist", "spotify:playlist:37i9") is None


def test_profile_counts_and_playlists(client):
    client.current_user.return_value = {
        "id": "noah",
        "display_name": "Noah",
        "images": [{"url": "avatar", "width": 300}],
        "external_urls": {"spotify": "https://open.spotify.com/user/noah"},
    }
    client.current_user_saved_tracks.return_value = {"total": 1234}
    client.current_user_saved_albums.return_value = {"total": 12}
    client.current_user_followed_artists.return_value = {"artists": {"total": 40}}
    client.current_user_playlists.return_value = {
        "total": 2,
        "items": [
            {"name": "Chill", "items": {"total": 30}, "owner": {"display_name": "Noah"}},
            {"name": "Old", "tracks": {"total": 7}, "owner": {"display_name": "Friend"}},
        ],
    }
    profile = SpotifyAPI(client).profile()
    assert profile.display_name == "Noah" and profile.image_url == "avatar"
    assert (profile.liked_tracks, profile.saved_albums, profile.followed_artists) == (1234, 12, 40)
    assert profile.playlist_count == 2
    assert [(p.name, p.tracks, p.owner) for p in profile.playlists] == [
        ("Chill", 30, "Noah"),
        ("Old", 7, "Friend"),
    ]


def test_profile_tolerates_missing_permissions(client):
    client.current_user.return_value = {"id": "noah"}
    denied = spotipy.SpotifyException(403, -1, "insufficient scope")
    for method in (
        "current_user_saved_tracks",
        "current_user_saved_albums",
        "current_user_followed_artists",
        "current_user_playlists",
    ):
        getattr(client, method).side_effect = denied
    profile = SpotifyAPI(client).profile()
    assert profile.display_name == "noah"
    assert profile.liked_tracks is None and profile.playlist_count is None and profile.playlists == ()


def test_now_playing_nothing(client):
    client.current_playback.return_value = None
    assert SpotifyAPI(client).now_playing() is None
    client.current_playback.return_value = {"item": None, "is_playing": False}
    assert SpotifyAPI(client).now_playing() is None


def test_now_playing_episode(client):
    client.current_playback.return_value = {
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
