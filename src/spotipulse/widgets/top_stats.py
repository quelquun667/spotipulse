"""Top tracks & artists per period, with a live filter and cover/avatar preview."""

from __future__ import annotations

from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.markup import escape
from textual.widgets import DataTable, Input, Static, Tab, Tabs

from .. import palette
from ..api import TIME_RANGES, Artist, SpotifyAPIError, Track
from ..stats import format_clock, format_duration, rank_changes, total_runtime_ms
from . import LazyView, cover_art, fit_columns, placeholder_cover

TOP_ARTISTS_SHOWN = 50
TRACK_COLUMNS = [
    ("rank", "#", 3, 0),
    ("trend", "Trend", 5, 0),
    ("title", "Title", 12, 3),
    ("artist", "Artist", 10, 2),
    ("length", "Length", 6, 0),
]
ARTIST_COLUMNS = [
    ("rank", "#", 3, 0),
    ("trend", "Trend", 5, 0),
    ("artist", "Artist", 12, 2),
    ("genres", "Genres", 10, 3),
]
# Each period's trend compares it with the next longer one; "1 Year" has nothing longer.
REFERENCE_PERIOD = {"short_term": "medium_term", "medium_term": "long_term"}


def trend_cell(change: int | None, has_reference: bool) -> Text:
    if not has_reference:
        return Text("")
    if change is None:
        return Text("NEW", style=f"bold {palette.bright()}")
    if change > 0:
        return Text(f"▲ {change}", style=palette.bright())
    if change < 0:
        return Text(f"▼ {-change}", style=palette.red())
    return Text("=", style="dim")


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
        self._track_trends: dict[str, int | None] = {}
        self._artist_trends: dict[str, int | None] = {}
        self._has_reference = False

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
                yield cover_art(placeholder_cover(), id="top-art", classes="art")
                yield Static("", id="top-art-caption")

    def on_mount(self) -> None:
        self.call_after_refresh(self._fit_columns)

    def on_resize(self) -> None:
        self.call_after_refresh(self._fit_columns)

    def _fit_columns(self) -> None:
        changed = fit_columns(self.query_one("#top-tracks", DataTable), TRACK_COLUMNS)
        changed = fit_columns(self.query_one("#top-artists", DataTable), ARTIST_COLUMNS) or changed
        if changed:
            self._render_tables()

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
        track_trends: dict[str, int | None] = {}
        artist_trends: dict[str, int | None] = {}
        reference_period = REFERENCE_PERIOD.get(time_range)
        if reference_period:
            try:
                reference = self.app.get_top(reference_period)
            except SpotifyAPIError:
                reference_period = None
            else:
                track_trends = rank_changes([t.id for t in data.tracks], [t.id for t in reference.tracks])
                artist_trends = rank_changes([a.id for a in data.artists], [a.id for a in reference.artists])
        _, summary = self.app.listening_summary(time_range)
        self.app.call_from_thread(
            self._loaded,
            time_range,
            data.tracks,
            data.artists[:TOP_ARTISTS_SHOWN],
            summary,
            (track_trends, artist_trends, reference_period),
        )

    def _failed(self, message: str) -> None:
        self.stale = True
        self.query_one("#top-summary", Static).update(f"[red]{escape(message)}[/red]")

    def _loaded(
        self,
        time_range: str,
        tracks: list[Track],
        artists: list[Artist],
        summary: str,
        trends: tuple[dict[str, int | None], dict[str, int | None], str | None],
    ) -> None:
        if time_range != self.app.period:
            return
        self._loaded_period = time_range
        self._tracks, self._artists = tracks, artists
        self._track_trends, self._artist_trends, reference_period = trends
        self._has_reference = reference_period is not None
        runtime = format_duration(total_runtime_ms(tracks))
        if reference_period:
            trend_note = (
                f"Trend: rank vs your last {TIME_RANGES[reference_period].lower()} (▲ up, ▼ down, NEW)"
            )
        else:
            trend_note = "Trend: nothing longer than 1 year to compare with"
        self.query_one("#top-summary", Static).update(
            f"{summary}\n[dim]Top {len(tracks)} tracks back to back: {runtime} · {trend_note}[/dim]"
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
        artists = self.query_one("#top-artists", DataTable)
        if not tracks.columns or not artists.columns:
            return  # columns get laid out once the tables have a size, then this runs again
        tracks.clear()
        for rank, track in enumerate(self._tracks, start=1):
            if needle and not track_matches(track, needle):
                continue
            tracks.add_row(
                str(rank),
                trend_cell(self._track_trends.get(track.id), self._has_reference),
                Text(track.name),
                Text(track.artist_line),
                format_clock(track.duration_ms),
                key=f"t{rank - 1}",
            )
        artists.clear()
        for rank, artist in enumerate(self._artists, start=1):
            if needle and not artist_matches(artist, needle):
                continue
            genres = ", ".join((artist.genres or ())[:3]) or "—"
            artists.add_row(
                str(rank),
                trend_cell(self._artist_trends.get(artist.id), self._has_reference),
                Text(artist.name),
                Text(genres, style="dim"),
                key=f"a{rank - 1}",
            )

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
        self.app.call_from_thread(setattr, self.query_one("#top-art"), "image", image)
