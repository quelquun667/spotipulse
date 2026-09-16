"""Smoke test: the whole TUI runs headless against a fake Spotify API."""

import asyncio
from datetime import UTC, datetime, timedelta

from spotipulse.api import NowPlaying, PlayedItem, PlaylistInfo, Profile
from spotipulse.app import SpotipulseApp
from spotipulse.config import Config
from spotipulse.db import HistoryDB

from conftest import make_artist, make_track


class FakeAPI:
    def __init__(self):
        self.tracks = [make_track(i) for i in range(20)]

    def now_playing(self):
        return NowPlaying(
            self.tracks[0],
            45_000,
            True,
            device_name="PC",
            device_type="Computer",
            volume=50,
            shuffle=True,
            repeat="context",
            context_type="playlist",
            context_uri="spotify:playlist:x",
        )

    def queue(self, limit=5):
        return self.tracks[1 : 1 + limit]

    def context_name(self, context_type, uri):
        return "Chill Vibes"

    def profile(self):
        return Profile("Noah", "noah", None, None, 10, 2, 3, 1, (PlaylistInfo("Chill", 30, "Noah"),))

    def top_tracks(self, time_range, limit=20):
        # a different order per period, so trends aren't all "="
        order = self.tracks if time_range == "short_term" else list(reversed(self.tracks))
        return order[:limit]

    def top_artists(self, time_range, limit=20):
        return [make_artist(i, ("indie pop",)) for i in range(limit)]

    def artist(self, artist_id):
        raise AssertionError("top artists already carry genres")

    def recently_played(self, limit=50):
        now = datetime.now(UTC)
        return [PlayedItem(self.tracks[i % 20], now - timedelta(minutes=5 * i)) for i in range(limit)]

    def image(self, url):
        return None


def test_app_runs_through_every_tab(tmp_path):
    db = HistoryDB(":memory:")
    app = SpotipulseApp(FakeAPI(), db, Config("id", "secret", export_dir=tmp_path), splash=False)

    async def drive():
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.pause(0.5)
            for key in "234561":
                await pilot.press(key)
                await pilot.pause(0.3)
            await pilot.press("y")
            await pilot.press("e")
            await pilot.pause(1.5)

    asyncio.run(drive())
    # the now-playing poll logged the track (45 s in, past the 30 s threshold)
    assert db.play_count() == 1
    assert list(tmp_path.glob("spotipulse-recap-*.png"))


def test_tabs_switch_with_digits_and_azerty_top_row(tmp_path):
    app = SpotipulseApp(FakeAPI(), HistoryDB(":memory:"), Config("id", "secret"), splash=False)
    seen = []

    async def drive():
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.pause(0.3)
            # AZERTY without Shift: & é " ' (   then the plain digits
            keys = ("é", "quotation_mark", "apostrophe", "left_parenthesis", "minus", "ampersand", "6", "1")
            for key in keys:
                await pilot.press(key)
                await pilot.pause(0.1)
                seen.append(app.query_one("#tabs").active)

    asyncio.run(drive())
    assert seen == ["top", "genres", "history", "recent", "profile", "now", "profile", "now"]
