"""Top tracks & artists per period, with a live filter and cover/avatar preview."""

from __future__ import annotations

from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.markup import escape
from textual.widgets import DataTable, Input, Static, Tab, Tabs

from ..api import TIME_RANGES, Artist, SpotifyAPIError, Track
from ..stats import format_clock, format_duration, total_runtime_ms
from . import CoverArt, LazyView, placeholder_cover

TOP_ARTISTS_SHOWN = 20


def track_matches(track: Track, needle: str) -> bool:
    haystack = " ".join((track.name, track.artist_line, track.album)).lower()
    return all(word in haystack for word in needle.lower().split())


def artist_matches(artist: Artist, needle: str) -> bool:
    haystack = " ".join((artist.name, *(artist.genres or ()))).lower()
    return all(word in haystack for word in needle.lower().split())


class TopStatsView(LazyView):
    BINDINGS = [
        Binding("/", "focus_filter", "Filter"),
        Binding("escape", "clear_filter", "Clear filter", show=False),
        Binding("left", "shift_period(-1)", "Prev period", show=False),
        Binding("right", "shift_period(1)", "Next period", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._tracks: list[Track] = []
        self._artists: list[Artist] = []
        self._loaded_period: str | None = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="top-header"):
            yield Tabs(*(Tab(label, id=key) for key, label in TIME_RANGES.items()), id="period-tabs")
        yield Static("", id="top-summary")
        yield Input(placeholder="Type to filter tracks & artists…  ( / )", id="top-filter")
        with Horizontal(id="top-body"):
            with Vertical(classes="panel", id="top-tracks-panel") as tracks_panel:
                tracks_panel.border_title = "Top Tracks"
                yield DataTable(id="top-tracks", cursor_type="row", zebra_stripes=False)
            with Vertical(classes="panel", id="top-artists-panel") as artists_panel:
                artists_panel.border_title = "Top Artists"
                yield DataTable(id="top-artists", cursor_type="row")
            with Vertical(classes="panel", id="top-art-panel") as art_panel:
                art_panel.border_title = "Cover"
                yield CoverArt(placeholder_cover(), id="top-art", classes="art")
                yield Static("", id="top-art-caption")

    def on_mount(self) -> None:
        tracks = self.query_one("#top-tracks", DataTable)
        tracks.add_column("#", key="rank", width=3)
        tracks.add_column("Title", key="title", width=28)
        tracks.add_column("Artist", key="artist", width=20)
        tracks.add_column("Length", key="length", width=6)
        artists = self.query_one("#top-artists", DataTable)
        artists.add_column("#", key="rank", width=3)
        artists.add_column("Artist", key="artist", width=20)
        artists.add_column("Genres", key="genres", width=24)

    # ---------- period ----------

    def period_changed(self, time_range: str) -> None:
        tabs = self.query_one("#period-tabs", Tabs)
        if tabs.active != time_range:
            tabs.active = time_range
        if time_range != self._loaded_period:
            self.stale = True
            if self.is_visible_tab():
                self.activate()

    @on(Tabs.TabActivated, "#period-tabs")
    def _period_tab(self, event: Tabs.TabActivated) -> None:
        if event.tab.id and event.tab.id != self.app.period:
            self.app.period = event.tab.id

    def action_shift_period(self, step: int) -> None:
        keys = list(TIME_RANGES)
        index = (keys.index(self.app.period) + step) % len(keys)
        self.app.period = keys[index]

    # ---------- loading ----------

    def load(self) -> None:
        self.query_one("#top-summary", Static).update(f"Loading {TIME_RANGES[self.app.period]}…")
        self._fetch(self.app.period)

    @work(thread=True, exclusive=True, group="top")
    def _fetch(self, time_range: str) -> None:
        try:
            data = self.app.get_top(time_range)
        except SpotifyAPIError as exc:
            self.app.call_from_thread(self._failed, str(exc))
            return
        _, summary = self.app.listening_summary(time_range)
        self.app.call_from_thread(
            self._loaded, time_range, data.tracks, data.artists[:TOP_ARTISTS_SHOWN], summary
        )

    def _failed(self, message: str) -> None:
        self.stale = True
        self.query_one("#top-summary", Static).update(f"[red]{escape(message)}[/red]")

    def _loaded(self, time_range: str, tracks: list[Track], artists: list[Artist], summary: str) -> None:
        if time_range != self.app.period:
            return
        self._loaded_period = time_range
        self._tracks, self._artists = tracks, artists
        runtime = format_duration(total_runtime_ms(tracks))
        self.query_one("#top-summary", Static).update(
            f"{summary}\n[dim]Top {len(tracks)} tracks back to back: {runtime}[/dim]"
        )
        self._render_tables()

    # ---------- filter ----------

    def action_focus_filter(self) -> None:
        self.query_one("#top-filter", Input).focus()

    def action_clear_filter(self) -> None:
        box = self.query_one("#top-filter", Input)
        box.value = ""
        self.query_one("#top-tracks", DataTable).focus()

    @on(Input.Changed, "#top-filter")
    def _filter_changed(self) -> None:
        self._render_tables()

    @on(Input.Submitted, "#top-filter")
    def _filter_submitted(self) -> None:
        self.query_one("#top-tracks", DataTable).focus()

    def _render_tables(self) -> None:
        needle = self.query_one("#top-filter", Input).value.strip()
        tracks = self.query_one("#top-tracks", DataTable)
        tracks.clear()
        for rank, track in enumerate(self._tracks, start=1):
            if needle and not track_matches(track, needle):
                continue
            tracks.add_row(
                str(rank),
                Text(track.name),
                Text(track.artist_line),
                format_clock(track.duration_ms),
                key=f"t{rank - 1}",
            )
        artists = self.query_one("#top-artists", DataTable)
        artists.clear()
        for rank, artist in enumerate(self._artists, start=1):
            if needle and not artist_matches(artist, needle):
                continue
            genres = ", ".join((artist.genres or ())[:3]) or "—"
            artists.add_row(str(rank), Text(artist.name), Text(genres, style="dim"), key=f"a{rank - 1}")

    # ---------- art preview ----------

    @on(DataTable.RowHighlighted)
    def _row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        key = event.row_key.value if event.row_key else None
        if not key:
            return
        index = int(key[1:])
        if key[0] == "t" and index < len(self._tracks):
            item = self._tracks[index]
            caption = (
                f"[b]{escape(item.name)}[/b]\n{escape(item.artist_line)}\n[dim]{escape(item.album)}[/dim]"
            )
        elif key[0] == "a" and index < len(self._artists):
            item = self._artists[index]
            genres = ", ".join(item.genres or ()) or "No genres listed"
            caption = f"[b]{escape(item.name)}[/b]\n[dim]{escape(genres)}[/dim]"
        else:
            return
        self.query_one("#top-art-panel").border_title = "Cover" if key[0] == "t" else "Artist"
        self.query_one("#top-art-caption", Static).update(caption)
        self._load_art(item.image_url)

    @work(thread=True, exclusive=True, group="top-art")
    def _load_art(self, url: str | None) -> None:
        image = self.app.api.image(url) or placeholder_cover()
        self.app.call_from_thread(setattr, self.query_one("#top-art", CoverArt), "image", image)
