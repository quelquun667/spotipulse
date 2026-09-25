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

    def me_brief(self):
        return "Noah", None

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


def test_compact_view_and_help_toggle():
    app = SpotipulseApp(FakeAPI(), HistoryDB(":memory:"), Config("id", "secret"), splash=False)
    screens = []

    async def drive():
        async with app.run_test(size=(60, 10)) as pilot:
            await pilot.pause(0.5)
            for key in ("c", "question_mark", "escape", "c", "c", "3"):
                await pilot.press(key)
                await pilot.pause(0.2)
                screens.append(type(app.screen).__name__)
            screens.append(app.query_one("#tabs").active)

    asyncio.run(drive())
    assert screens == ["MiniScreen", "HelpScreen", "MiniScreen", "Screen", "MiniScreen", "Screen", "genres"]


def test_starts_in_compact_view_and_shows_the_track():
    app = SpotipulseApp(FakeAPI(), HistoryDB(":memory:"), Config("id", "secret"), mini=True)
    seen = {}

    async def drive():
        async with app.run_test(size=(70, 9)) as pilot:
            await pilot.pause(0.8)
            seen["screen"] = type(app.screen).__name__
            seen["title"] = str(app.screen.query_one("#mini-title").render())

    asyncio.run(drive())
    assert seen["screen"] == "MiniScreen"
    assert "Track 0" in seen["title"]


def test_cached_top_shows_first_then_refreshes(tmp_path):
    from spotipulse.cache import DiskCache, encode_top

    disk = DiskCache(tmp_path)
    stale = [make_track(99)]
    disk.save("top_short_term", encode_top(stale, [], []))
    api = FakeAPI()
    app = SpotipulseApp(api, HistoryDB(":memory:"), Config("id", "secret"), splash=False, disk=disk)
    seen = []

    async def drive():
        async with app.run_test(size=(140, 45)) as pilot:
            seen.append(app.get_top("short_term").tracks[0].id)  # instant, from disk
            await pilot.pause(1.0)
            seen.append(app.get_top("short_term").tracks[0].id)  # refreshed in the background

    asyncio.run(drive())
    assert seen == ["track99", "track0"]
    # and the fresh copy was written back for next launch
    assert disk.load("top_short_term")[0]["tracks"][0]["id"] == "track0"


def _run(app, keys, size=(140, 45), pause=0.3):
    screens = []

    async def drive():
        async with app.run_test(size=size) as pilot:
            await pilot.pause(0.5)
            for key in keys:
                await pilot.press(key)
                await pilot.pause(pause)
                screens.append(type(app.screen).__name__)

    asyncio.run(drive())
    return screens


def test_shift_e_picks_a_format_and_exports_it(tmp_path):
    app = SpotipulseApp(
        FakeAPI(), HistoryDB(":memory:"), Config("id", "secret", export_dir=tmp_path), splash=False
    )
    screens = _run(app, ["E", "2"], pause=1.5)
    assert screens[0] == "ExportScreen"
    assert [p.name.endswith("-story.png") for p in tmp_path.glob("*.png")] == [True]


def test_escape_cancels_the_format_menu(tmp_path):
    app = SpotipulseApp(
        FakeAPI(), HistoryDB(":memory:"), Config("id", "secret", export_dir=tmp_path), splash=False
    )
    screens = _run(app, ["E", "escape"])
    assert screens == ["ExportScreen", "Screen"]
    assert not list(tmp_path.glob("*.png"))


def test_default_format_comes_from_the_config(tmp_path):
    config = Config("id", "secret", export_dir=tmp_path, recap_format="square")
    app = SpotipulseApp(FakeAPI(), HistoryDB(":memory:"), config, splash=False)
    _run(app, ["e"], pause=1.5)
    assert [p.name.endswith("-square.png") for p in tmp_path.glob("*.png")] == [True]


def test_t_toggles_the_light_theme():
    app = SpotipulseApp(FakeAPI(), HistoryDB(":memory:"), Config("id", "secret"), splash=False)
    themes = []

    async def drive():
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.pause(0.3)
            themes.append(app.theme)
            await pilot.press("t")
            await pilot.pause(0.3)
            themes.append(app.theme)
            await pilot.press("t")
            await pilot.pause(0.3)
            themes.append(app.theme)

    asyncio.run(drive())
    assert themes == ["spotipulse", "spotipulse-light", "spotipulse"]


def test_light_theme_from_config():
    app = SpotipulseApp(FakeAPI(), HistoryDB(":memory:"), Config("id", "secret", theme="light"), splash=False)
    seen = {}

    async def drive():
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.pause(0.3)
            seen["theme"] = app.theme

    asyncio.run(drive())
    assert seen["theme"] == "spotipulse-light"


def test_equalizer_follows_the_animations_setting():
    from spotipulse.widgets.equalizer import Equalizer

    counts = {}
    for animations in (True, False):
        app = SpotipulseApp(
            FakeAPI(), HistoryDB(":memory:"), Config("id", "secret", animations=animations), splash=False
        )

        async def drive(app=app, animations=animations):
            async with app.run_test(size=(140, 45)) as pilot:
                await pilot.pause(0.5)
                counts[animations] = len(app.query(Equalizer))

        asyncio.run(drive())
    assert counts == {True: 1, False: 0}


def test_accent_from_cover_tints_now_playing():
    from PIL import Image

    class ColorfulAPI(FakeAPI):
        def image(self, url):
            return Image.new("RGB", (32, 32), (200, 30, 30))

    tracks = FakeAPI().tracks
    api = ColorfulAPI()
    api.tracks = [t.__class__(**{**t.__dict__, "image_url": "cover"}) for t in tracks]
    config = Config("id", "secret", accent_from_cover=True)
    app = SpotipulseApp(api, HistoryDB(":memory:"), config, splash=False)
    seen = {}

    async def drive():
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.pause(1.0)
            seen["accent"] = app.query_one(NowPlayingView).accent

    from spotipulse.widgets.now_playing import NowPlayingView

    asyncio.run(drive())
    red, green, blue = (int(seen["accent"][i : i + 2], 16) for i in (1, 3, 5))
    assert red > green and red > blue


def test_compact_view_uses_the_cover_tint():
    from PIL import Image

    from spotipulse.widgets.now_playing import NowPlayingView

    class ColourfulAPI(FakeAPI):
        def __init__(self):
            super().__init__()
            self.tracks = [t.__class__(**{**t.__dict__, "image_url": "cover"}) for t in self.tracks]

        def image(self, url):
            return Image.new("RGB", (32, 32), (30, 60, 220))

    app = SpotipulseApp(
        ColourfulAPI(), HistoryDB(":memory:"), Config("id", "secret", accent_from_cover=True), splash=False
    )
    seen = {}

    async def drive():
        async with app.run_test(size=(90, 14)) as pilot:
            await pilot.pause(1.0)
            seen["accent"] = app.query_one(NowPlayingView).accent
            await pilot.press("c")
            await pilot.pause(0.6)
            mini = app.screen
            seen["artist"] = str(mini.query_one("#mini-artist").render())
            seen["border"] = mini.query_one("#mini").styles.border_top[1].hex.upper()

    asyncio.run(drive())
    assert seen["accent"] is not None
    assert seen["border"] == seen["accent"].upper()  # the compact view borrows the same colour
    assert seen["artist"]  # and still shows the artist
