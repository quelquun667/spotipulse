"""Current track: cover art, title/artist/album, live progress bar."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.markup import escape
from textual.widgets import ProgressBar, Static

from ..api import NowPlaying, SpotifyAPIError
from ..stats import format_clock
from . import CoverArt, placeholder_cover

# Spotify counts a stream after 30 s; shorter tracks count at half their length.
COUNT_AFTER_MS = 30_000


class NowPlayingView(Vertical):
    def __init__(self) -> None:
        super().__init__()
        self._state: NowPlaying | None = None
        self._state_at = 0.0  # monotonic time the state was fetched
        self._cover_url: str | None = "unset"
        self._current_key: str | None = None
        self._last_progress = 0
        self._logged = False
        self._error_shown = False

    def compose(self) -> ComposeResult:
        with Horizontal(id="np-body"):
            with Vertical(id="np-art-box"):
                yield CoverArt(placeholder_cover(), id="np-art")
            with Vertical(id="np-info"):
                yield Static("CONNECTING…", id="np-status")
                yield Static("", id="np-title")
                yield Static("", id="np-artist")
                yield Static("", id="np-album")
                yield ProgressBar(total=100, show_eta=False, show_percentage=False, id="np-progress")
                yield Static("", id="np-time")

    def on_mount(self) -> None:
        self.poll()
        self.set_interval(self.app.config.refresh_interval, self.poll)
        self.set_interval(0.5, self._tick)

    @work(thread=True, exclusive=True, group="now-playing")
    def poll(self) -> None:
        try:
            state = self.app.api.now_playing()
        except SpotifyAPIError as exc:
            if not self._error_shown:
                self._error_shown = True
                self.app.call_from_thread(self.app.notify, str(exc), severity="error")
            return
        self._error_shown = False
        self._log_history(state)
        cover = None
        url = state.track.image_url if state else None
        if url != self._cover_url:
            cover = self.app.api.image(url) or placeholder_cover()
        self.app.call_from_thread(self._show, state, url, cover)

    def _log_history(self, state: NowPlaying | None) -> None:
        if not state or not state.is_playing or state.kind != "track":
            return
        track = state.track
        replayed = track.id == self._current_key and state.progress_ms + 30_000 < self._last_progress
        if track.id != self._current_key or replayed:
            self._current_key = track.id
            self._logged = False
        self._last_progress = state.progress_ms
        threshold = min(COUNT_AFTER_MS, max(track.duration_ms // 2, 1))
        if not self._logged and state.progress_ms >= threshold:
            started = datetime.now(UTC) - timedelta(milliseconds=state.progress_ms)
            self.app.db.record_play(track, started)
            self._logged = True

    def _show(self, state: NowPlaying | None, url: str | None, cover) -> None:
        self._state = state
        self._state_at = time.monotonic()
        if cover is not None:
            self._cover_url = url
            self.query_one("#np-art", CoverArt).image = cover
        status = self.query_one("#np-status", Static)
        if state is None:
            status.update("NOTHING PLAYING")
            self.query_one("#np-title", Static).update("Start something on Spotify")
            self.query_one("#np-artist", Static).update("spotipulse will pick it up within a few seconds.")
            self.query_one("#np-album", Static).update("")
            self.query_one("#np-progress", ProgressBar).update(total=100, progress=0)
            self.query_one("#np-time", Static).update("")
            return
        track = state.track
        label = "PODCAST" if state.kind == "episode" else "NOW PLAYING"
        status.update(f"▶  {label}" if state.is_playing else "⏸  PAUSED")
        self.query_one("#np-title", Static).update(escape(track.name))
        self.query_one("#np-artist", Static).update(escape(track.artist_line))
        self.query_one("#np-album", Static).update(escape(track.album))
        self._tick()

    def _tick(self) -> None:
        state = self._state
        if state is None:
            return
        progress = state.progress_ms
        if state.is_playing:
            progress += int((time.monotonic() - self._state_at) * 1000)
        duration = max(state.track.duration_ms, 1)
        progress = min(progress, duration)
        self.query_one("#np-progress", ProgressBar).update(total=duration, progress=progress)
        self.query_one("#np-time", Static).update(f"{format_clock(progress)} / {format_clock(duration)}")
