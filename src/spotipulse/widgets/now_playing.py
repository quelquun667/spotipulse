"""Current track: cover art, details, playback state, progress bar and what's up next."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.color import Color
from textual.containers import Horizontal, Vertical
from textual.markup import escape
from textual.widgets import Static

from .. import palette
from ..api import NowPlaying, SpotifyAPIError, Track
from ..stats import format_clock
from . import cover_art, placeholder_cover
from .equalizer import Equalizer

# Spotify counts a stream after 30 s; shorter tracks count at half their length.
COUNT_AFTER_MS = 30_000
# The queue only changes when you add something, so it's fetched on track change or every so often.
QUEUE_REFRESH_S = 15
QUEUE_SIZE = 5

BORDER_RULES = ("border_top", "border_right", "border_bottom", "border_left", "border_title_color")

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
        text.append(value, style=f"bold {palette.bright()}" if active else "")

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


def progress_bar(position: int, duration: int, width: int, color: str) -> Text:
    """A thin line: played part in the accent color, the rest dimmed."""
    width = max(1, width)
    done = round(width * position / max(duration, 1))
    return Text.assemble(("━" * done, color), ("━" * (width - done), "dim"))


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
        text.append(f"  {track.artist_line}", style=palette.green())
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
        # Last values shown, read by the compact (mini) view.
        self.context_name: str | None = None
        self.queue: list[Track] = []
        # Cover-tinted accent (setting `accent_from_cover`); None means the theme's green.
        self.accent: str | None = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="np-body"):
            with Vertical(id="np-art-box"):
                yield cover_art(placeholder_cover(), id="np-art")
            with Vertical(id="np-info"):
                with Horizontal(id="np-status-row"):
                    if self.app.config.animations:
                        yield Equalizer(id="np-equalizer")
                    yield Static("CONNECTING…", id="np-status")
                yield Static("", id="np-title")
                yield Static("", id="np-artist")
                yield Static("", id="np-album")
                yield Static("", id="np-context")
                yield Static("", id="np-progress")
                yield Static("", id="np-time")
                yield Static("", id="np-playback")
        with Vertical(id="np-queue", classes="panel") as queue_panel:
            queue_panel.border_title = "Up next"
            yield Static("", id="np-queue-list")

    def on_mount(self) -> None:
        self.poll()
        self._poll_timer = self.set_interval(self.app.config.refresh_interval, self.poll)
        self.set_interval(0.5, self._tick)

    # ---------- live settings (Settings screen) ----------

    def set_refresh_interval(self, seconds: float) -> None:
        self._poll_timer.stop()
        self._poll_timer = self.set_interval(seconds, self.poll)

    def set_equalizer(self, enabled: bool) -> None:
        existing = list(self.query(Equalizer))
        if enabled and not existing:
            equalizer = Equalizer(id="np-equalizer")
            self.query_one("#np-status-row").mount(equalizer, before=self.query_one("#np-status"))
            equalizer.set_color(self.accent)
            equalizer.call_after_refresh(equalizer.set_playing, bool(self._state and self._state.is_playing))
        elif not enabled:
            for equalizer in existing:
                equalizer.remove()

    def refresh_accent(self) -> None:
        """Recompute (or drop) the cover color after `accent_from_cover` changed."""
        self._cover_url = "unset"  # the next poll re-reads the cover and its color
        if not self.app.config.accent_from_cover:
            self.set_accent(None)
        self.poll()

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
        accent = self.accent
        url = state.track.image_url if state else None
        if url != self._cover_url:
            image = api.image(url)
            cover = image or placeholder_cover()
            if self.app.config.accent_from_cover:
                brightness = 0.85 if self.app.current_theme.dark else 0.5
                accent = palette.to_hex(palette.accent_color(image, brightness)) if image else None

        context_name = api.context_name(state.context_type, state.context_uri) if state else None

        track_id = state.track.id if state else None
        if track_id != self._queue_track or time.monotonic() - self._queue_at > QUEUE_REFRESH_S:
            try:
                self._queue = api.queue(QUEUE_SIZE) if state else []
            except SpotifyAPIError:
                self._queue = []
            self._queue_track = track_id
            self._queue_at = time.monotonic()

        self.app.call_from_thread(self._show, state, url, cover, context_name, list(self._queue), accent)

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
        accent: str | None = None,
    ) -> None:
        self._state = state
        self._state_at = time.monotonic()
        self.context_name = context_name
        self.queue = queue
        if cover is not None:
            self._cover_url = url
            self.query_one("#np-art").image = cover
        if accent != self.accent:
            self.set_accent(accent)
        for equalizer in self.query(Equalizer):
            equalizer.set_playing(bool(state and state.is_playing))
        status = self.query_one("#np-status", Static)
        if state is None:
            status.update("NOTHING PLAYING")
            self.query_one("#np-title", Static).update("Start something on Spotify")
            self.query_one("#np-artist", Static).update("spotipulse will pick it up within a few seconds.")
            for widget_id in ("#np-album", "#np-context", "#np-time", "#np-playback"):
                self.query_one(widget_id, Static).update("")
            self.query_one("#np-progress", Static).update("")
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

    @property
    def state(self) -> NowPlaying | None:
        return self._state

    def progress(self) -> tuple[int, int]:
        """(position, duration) in ms, moved forward locally between polls."""
        state = self._state
        if state is None:
            return 0, 0
        progress = state.progress_ms
        if state.is_playing:
            progress += int((time.monotonic() - self._state_at) * 1000)
        duration = max(state.track.duration_ms, 1)
        return min(progress, duration), duration

    def set_accent(self, accent: str | None) -> None:
        """Tint the tab with a cover color (None = back to the theme's colors), fading the text in."""
        self.accent = accent
        targets = ("#np-status", "#np-artist")
        for selector in targets:
            widget = self.query_one(selector)
            if accent is None:
                widget.styles.clear_rule("color")
            else:
                widget.styles.animate("color", Color.parse(accent), duration=0.4)
        for selector in ("#np-body", "#np-queue"):
            widget = self.query_one(selector)
            if accent is None:
                # "border" is four rules under the hood: clearing it by that name would do nothing,
                # and the panel would keep the color of whatever was playing.
                for rule in BORDER_RULES:
                    widget.styles.clear_rule(rule)
            else:
                widget.styles.border = ("round", accent)
                widget.styles.border_title_color = accent
        for equalizer in self.query(Equalizer):
            equalizer.set_color(accent)
        self._tick()

    def _tick(self) -> None:
        if self._state is None:
            return
        progress, duration = self.progress()
        bar = self.query_one("#np-progress", Static)
        width = bar.content_region.width or 40
        bar.update(progress_bar(progress, duration, width, self.accent or palette.green()))
        self.query_one("#np-time", Static).update(f"{format_clock(progress)} / {format_clock(duration)}")
