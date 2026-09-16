"""Current track: cover art, details, playback state, progress bar and what's up next."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.markup import escape
from textual.widgets import ProgressBar, Static

from ..api import NowPlaying, SpotifyAPIError, Track
from ..stats import format_clock
from . import CoverArt, placeholder_cover

# Spotify counts a stream after 30 s; shorter tracks count at half their length.
COUNT_AFTER_MS = 30_000
# The queue only changes when you add something, so it's fetched on track change or every so often.
QUEUE_REFRESH_S = 15
QUEUE_SIZE = 5

REPEAT_LABELS = {"off": "off", "context": "all", "track": "one"}
CONTEXT_LABELS = {"playlist": "playlist", "album": "album", "artist": "artist", "show": "podcast"}


def context_line(state: NowPlaying, name: str | None) -> str:
    """'From playlist Chill Vibes' / 'From Liked Songs' / '' when unknown."""
    if not state.context_type and not state.context_uri:
        return ""
    if state.context_type == "collection" or (state.context_uri or "").endswith(":collection"):
        return "From [b]Liked Songs[/b]"
    kind = CONTEXT_LABELS.get(state.context_type or "", state.context_type or "")
    if name:
        return f"From {kind} [b]{escape(name)}[/b]"
    return f"From a {kind}" if kind else ""


def playback_line(state: NowPlaying) -> Text:
    text = Text()

    def field(label: str, value: str, active: bool = True) -> None:
        if text:
            text.append("    ")
        text.append(f"{label} ", style="dim")
        text.append(value, style="bold #1ED760" if active else "")

    if state.device_name:
        device = state.device_name
        if state.device_type:
            device += f" ({state.device_type.title()})"
        field("Device", device, active=False)
    if state.volume is not None:
        field("Volume", f"{state.volume}%", active=False)
    field("Shuffle", "on" if state.shuffle else "off", active=state.shuffle)
    field("Repeat", REPEAT_LABELS.get(state.repeat, state.repeat), active=state.repeat != "off")
    return text


def queue_text(queue: list[Track]) -> Text:
    text = Text()
    if not queue:
        text.append("Nothing queued.", style="italic dim")
        return text
    for i, track in enumerate(queue, start=1):
        if i > 1:
            text.append("\n")
        text.append(f"{i}  ", style="dim")
        text.append(track.name, style="bold")
        text.append(f"  {track.artist_line}", style="#1DB954")
        text.append(f"  {format_clock(track.duration_ms)}", style="dim")
    return text


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
        self._queue: list[Track] = []
        self._queue_track: str | None = None
        self._queue_at = 0.0

    def compose(self) -> ComposeResult:
        with Horizontal(id="np-body"):
            with Vertical(id="np-art-box"):
                yield CoverArt(placeholder_cover(), id="np-art")
            with Vertical(id="np-info"):
                yield Static("CONNECTING…", id="np-status")
                yield Static("", id="np-title")
                yield Static("", id="np-artist")
                yield Static("", id="np-album")
                yield Static("", id="np-context")
                yield ProgressBar(total=100, show_eta=False, show_percentage=False, id="np-progress")
                yield Static("", id="np-time")
                yield Static("", id="np-playback")
        with Vertical(id="np-queue", classes="panel") as queue_panel:
            queue_panel.border_title = "Up next"
            yield Static("", id="np-queue-list")

    def on_mount(self) -> None:
        self.poll()
        self.set_interval(self.app.config.refresh_interval, self.poll)
        self.set_interval(0.5, self._tick)

    @work(thread=True, exclusive=True, group="now-playing")
    def poll(self) -> None:
        api = self.app.api
        try:
            state = api.now_playing()
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
            cover = api.image(url) or placeholder_cover()

        context_name = api.context_name(state.context_type, state.context_uri) if state else None

        track_id = state.track.id if state else None
        if track_id != self._queue_track or time.monotonic() - self._queue_at > QUEUE_REFRESH_S:
            try:
                self._queue = api.queue(QUEUE_SIZE) if state else []
            except SpotifyAPIError:
                self._queue = []
            self._queue_track = track_id
            self._queue_at = time.monotonic()

        self.app.call_from_thread(self._show, state, url, cover, context_name, list(self._queue))

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

    def _show(
        self,
        state: NowPlaying | None,
        url: str | None,
        cover,
        context_name: str | None,
        queue: list[Track],
    ) -> None:
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
            for widget_id in ("#np-album", "#np-context", "#np-time", "#np-playback"):
                self.query_one(widget_id, Static).update("")
            self.query_one("#np-progress", ProgressBar).update(total=100, progress=0)
            self.query_one("#np-queue-list", Static).update(queue_text([]))
            return
        track = state.track
        label = "PODCAST" if state.kind == "episode" else "NOW PLAYING"
        status.update(f"▶  {label}" if state.is_playing else "⏸  PAUSED")
        self.query_one("#np-title", Static).update(escape(track.name))
        self.query_one("#np-artist", Static).update(escape(track.artist_line))
        album = escape(track.album)
        if track.year:
            album = f"{album}  [dim]·[/dim]  {track.year}" if album else track.year
        self.query_one("#np-album", Static).update(album)
        self.query_one("#np-context", Static).update(context_line(state, context_name))
        self.query_one("#np-playback", Static).update(playback_line(state))
        self.query_one("#np-queue-list", Static).update(queue_text(queue))
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
