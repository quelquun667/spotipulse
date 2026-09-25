"""Compact view: just what's playing, readable in a tiny terminal window."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Static

from .. import palette
from ..stats import format_clock
from .now_playing import BORDER_RULES, REPEAT_LABELS, NowPlayingView, progress_bar


class MiniScreen(Screen):
    BINDINGS = [
        Binding("c,escape", "app.toggle_mini", "Full view"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="mini"):
            yield Static("", id="mini-title")
            yield Static("", id="mini-artist")
            with Horizontal(id="mini-progress-row"):
                yield Static("", id="mini-elapsed")
                yield Static("", id="mini-progress")
                yield Static("", id="mini-duration")
            yield Static("", id="mini-meta")
            yield Static("", id="mini-next")
            yield Static("[dim]c[/] full view   [dim]?[/] help   [dim]q[/] quit", id="mini-keys")

    def on_mount(self) -> None:
        self.app.fade_in(self.query_one("#mini"))
        self._update_view()
        self.set_interval(0.5, self._update_view)

    def _set_border(self, accent: str | None) -> None:
        """The compact view mirrors the Now Playing tab, cover tint included."""
        panel = self.query_one("#mini")
        if accent is None:
            for rule in BORDER_RULES:
                panel.styles.clear_rule(rule)
        else:
            panel.styles.border = ("round", accent)

    def _update_view(self) -> None:
        view = self.app.query_one(NowPlayingView)
        state = view.state
        accent = view.accent  # None = the theme's green
        self._set_border(accent)
        title = self.query_one("#mini-title", Static)
        if state is None:
            title.update(Text("Nothing playing", style="bold"))
            self.query_one("#mini-artist", Static).update(Text("Start something on Spotify", style="dim"))
            for widget_id in ("#mini-elapsed", "#mini-duration", "#mini-meta", "#mini-next"):
                self.query_one(widget_id, Static).update("")
            self.query_one("#mini-progress", Static).update("")
            return

        track = state.track
        heading = Text()
        heading.append("▶ " if state.is_playing else "⏸ ", style=f"bold {accent or palette.bright()}")
        heading.append(track.name, style="bold")
        title.update(heading)

        artist = Text(track.artist_line, style=accent or palette.green())
        if track.album:
            artist.append(f"  ·  {track.album}", style="dim")
        if track.year:
            artist.append(f"  ·  {track.year}", style="dim")
        self.query_one("#mini-artist", Static).update(artist)

        position, duration = view.progress()
        self.query_one("#mini-elapsed", Static).update(format_clock(position))
        self.query_one("#mini-duration", Static).update(format_clock(duration))
        bar = self.query_one("#mini-progress", Static)
        bar.update(
            progress_bar(position, duration, bar.content_region.width or 30, accent or palette.green())
        )

        meta = Text()
        parts = []
        if view.context_name:
            parts.append(("from ", view.context_name))
        if state.device_name:
            volume = f" {state.volume}%" if state.volume is not None else ""
            parts.append(("on ", f"{state.device_name}{volume}"))
        for i, (label, value) in enumerate(parts):
            if i:
                meta.append("  ·  ", style="dim")
            meta.append(label, style="dim")
            meta.append(value)
        highlight = accent or palette.bright()
        if state.shuffle:
            meta.append("  ·  shuffle", style=highlight)
        if state.repeat != "off":
            meta.append(f"  ·  repeat {REPEAT_LABELS.get(state.repeat, state.repeat)}", style=highlight)
        self.query_one("#mini-meta", Static).update(meta)

        next_line = Text()
        if view.queue:
            upcoming = view.queue[0]
            next_line.append("next  ", style="dim")
            next_line.append(upcoming.name, style="bold")
            next_line.append(f"  {upcoming.artist_line}", style="dim")
        self.query_one("#mini-next", Static).update(next_line)
