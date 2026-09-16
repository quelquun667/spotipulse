"""Recently played list with timestamps and cover art."""

from __future__ import annotations

from datetime import datetime

from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.markup import escape
from textual.widgets import DataTable, Static

from ..api import PlayedItem, SpotifyAPIError
from ..stats import format_clock
from . import CoverArt, LazyView, placeholder_cover


def format_played_at(played_at: datetime, now: datetime | None = None) -> str:
    local = played_at.astimezone()
    now = (now or datetime.now().astimezone()).astimezone(local.tzinfo)
    days = (now.date() - local.date()).days
    if days == 0:
        return f"Today {local:%H:%M}"
    if days == 1:
        return f"Yesterday {local:%H:%M}"
    return f"{local:%b %d %H:%M}"


class RecentView(LazyView):
    def __init__(self) -> None:
        super().__init__()
        self._items: list[PlayedItem] = []

    def compose(self) -> ComposeResult:
        yield Static("", id="recent-summary")
        with Horizontal(id="recent-body"):
            with Vertical(classes="panel") as panel:
                panel.border_title = "Recently Played"
                yield DataTable(id="recent-table", cursor_type="row")
            with Vertical(classes="panel", id="recent-art-panel") as art_panel:
                art_panel.border_title = "Cover"
                yield CoverArt(placeholder_cover(), id="recent-art", classes="art")
                yield Static("", id="recent-art-caption")

    def on_mount(self) -> None:
        table = self.query_one("#recent-table", DataTable)
        table.add_column("Played", key="played", width=16)
        table.add_column("Title", key="title")
        table.add_column("Artist", key="artist")
        table.add_column("Album", key="album")
        table.add_column("Length", key="length", width=6)

    def activate(self) -> None:
        # Always worth re-fetching when the tab is opened: it's a single request.
        self.load()

    def load(self) -> None:
        self.query_one("#recent-summary", Static).update("Loading…")
        self._fetch()

    @work(thread=True, exclusive=True, group="recent")
    def _fetch(self) -> None:
        try:
            items = self.app.api.recently_played(limit=50)
        except SpotifyAPIError as exc:
            self.app.call_from_thread(self._failed, str(exc))
            return
        self.app.call_from_thread(self._loaded, items)

    def _failed(self, message: str) -> None:
        self.query_one("#recent-summary", Static).update(f"[red]{escape(message)}[/red]")

    def _loaded(self, items: list[PlayedItem]) -> None:
        self._items = items
        self.query_one("#recent-summary", Static).update(
            f"[dim]Your last {len(items)} tracks, as reported by Spotify.[/dim]"
            if items
            else "[dim]Spotify has no recently played tracks for your account yet.[/dim]"
        )
        table = self.query_one("#recent-table", DataTable)
        table.clear()
        for index, item in enumerate(items):
            table.add_row(
                format_played_at(item.played_at),
                Text(item.track.name),
                Text(item.track.artist_line),
                Text(item.track.album, style="dim"),
                format_clock(item.track.duration_ms),
                key=str(index),
            )

    @on(DataTable.RowHighlighted, "#recent-table")
    def _row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key is None or event.row_key.value is None:
            return
        index = int(event.row_key.value)
        if index >= len(self._items):
            return
        item = self._items[index]
        self.query_one("#recent-art-caption", Static).update(
            f"[b]{escape(item.track.name)}[/b]\n{escape(item.track.artist_line)}\n"
            f"[dim]{escape(item.track.album)}\n{format_played_at(item.played_at)}[/dim]"
        )
        self._load_art(item.track.image_url)

    @work(thread=True, exclusive=True, group="recent-art")
    def _load_art(self, url: str | None) -> None:
        image = self.app.api.image(url) or placeholder_cover()
        self.app.call_from_thread(setattr, self.query_one("#recent-art", CoverArt), "image", image)
