"""`spotipulse --demo`: made-up data behind the same interface as the real API."""

import asyncio

from spotipulse.api import TIME_RANGES, SpotifyAPI
from spotipulse.app import SpotipulseApp
from spotipulse.config import Config
from spotipulse.demo import ARTISTS, TRACKS, DemoAPI, demo_history


def test_demo_api_implements_everything_the_app_calls():
    public = {name for name in dir(SpotifyAPI) if not name.startswith("_")} - {"from_oauth", "client", "disk"}
    assert public <= set(dir(DemoAPI))


def test_demo_data_is_consistent():
    api = DemoAPI()
    for time_range in TIME_RANGES:
        tracks = api.top_tracks(time_range, limit=50)
        artists = api.top_artists(time_range, limit=50)
        assert len(tracks) == len(TRACKS) and len({t.id for t in tracks}) == len(TRACKS)
        assert len(artists) == len(ARTISTS) and all(a.genres for a in artists)
    # periods rank things differently, so trends show movement
    assert api.top_tracks("short_term") != api.top_tracks("long_term")
    now = api.now_playing()
    assert now.is_playing and 0 <= now.progress_ms <= now.track.duration_ms
    assert len(api.queue(5)) == 5 and api.context_name("playlist", "x") == "Late Night Drive"
    assert len(api.recently_played(50)) == 50
    assert api.image("demo://cover/Soft Focus").size == (600, 600)
    assert api.image(None) is None


def test_demo_history_has_streaks_and_gaps():
    db = demo_history()
    days = db.daily_totals()
    assert db.play_count() > 300
    assert 30 <= len(days) <= 42


def test_demo_app_runs(tmp_path):
    app = SpotipulseApp(DemoAPI(), demo_history(), Config("demo", "demo", export_dir=tmp_path), splash=False)
    seen = {}

    async def drive():
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.pause(0.8)
            seen["now"] = str(app.query_one("#np-title").render())
            for key in "234561":
                await pilot.press(key)
                await pilot.pause(0.3)
            await pilot.press("e")
            await pilot.pause(2.0)

    asyncio.run(drive())
    assert seen["now"] in {title for title, *_ in TRACKS}
    assert list(tmp_path.glob("spotipulse-recap-*.png"))
