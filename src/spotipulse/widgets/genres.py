"""Top genres bar chart, aggregated from your top artists."""

from __future__ import annotations

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.markup import escape
from textual.widgets import Static

from ..api import TIME_RANGES, SpotifyAPIError
from ..genres import GenreCount
from . import LazyView

LABEL_WIDTH = 26


def render_chart(genres: list[GenreCount], width: int, artist_total: int) -> Text:
    """Horizontal bars; the longest bar fills the available width."""
    text = Text()
    if not genres:
        text.append("Spotify didn't list any genres for your top artists in this period.", style="italic dim")
        return text
    peak = max(g.count for g in genres)
    count_width = len(str(peak)) + 12
    bar_space = max(10, width - LABEL_WIDTH - count_width - 2)
    for i, genre in enumerate(genres):
        label = genre.genre.title()
        if len(label) > LABEL_WIDTH - 1:
            label = label[: LABEL_WIDTH - 2] + "…"
        exact = bar_space * genre.count / peak
        full = int(exact)
        partial = " ▏▎▍▌▋▊▉"[int((exact - full) * 8)]
        bar = "█" * full + (partial if partial != " " else "")
        style = "bold #1ED760" if i < 3 else "#1DB954"
        text.append(f"{label:<{LABEL_WIDTH}}", style="bold" if i < 3 else "")
        text.append(bar, style=style)
        share = genre.count / artist_total * 100 if artist_total else 0
        text.append(f"  {genre.count} ({share:.0f}%)\n", style="dim")
    return text


class GenresView(LazyView):
    def __init__(self) -> None:
        super().__init__()
        self._genres: list[GenreCount] = []
        self._artist_total = 0
        self._loaded_period: str | None = None

    def compose(self) -> ComposeResult:
        yield Static("", id="genres-title")
        yield Static("", id="genres-chart", classes="panel")

    def period_changed(self, time_range: str) -> None:
        if time_range != self._loaded_period:
            self.stale = True
            if self.is_visible_tab():
                self.activate()

    def load(self) -> None:
        self.query_one("#genres-title", Static).update(f"Loading {TIME_RANGES[self.app.period]}…")
        self._fetch(self.app.period)

    @work(thread=True, exclusive=True, group="genres")
    def _fetch(self, time_range: str) -> None:
        try:
            data = self.app.get_top(time_range)
        except SpotifyAPIError as exc:
            self.app.call_from_thread(self._failed, str(exc))
            return
        self.app.call_from_thread(self._loaded, time_range, data.genres, len(data.artists))

    def _failed(self, message: str) -> None:
        self.stale = True
        self.query_one("#genres-title", Static).update(f"[red]{escape(message)}[/red]")

    def _loaded(self, time_range: str, genres: list[GenreCount], artist_total: int) -> None:
        if time_range != self.app.period:
            return
        self._loaded_period = time_range
        self._genres, self._artist_total = genres, artist_total
        self.query_one("#genres-title", Static).update(
            f"[b $primary]Top genres[/] · last {TIME_RANGES[time_range].lower()} · "
            f"from your top {artist_total} artists   [dim](w / m / y to switch period)[/dim]"
        )
        self.query_one("#genres-chart").border_title = TIME_RANGES[time_range]
        self._redraw()

    def on_resize(self) -> None:
        self._redraw()

    def _redraw(self) -> None:
        if self._loaded_period is None:
            return
        chart = self.query_one("#genres-chart", Static)
        width = (chart.content_region.width or self.size.width - 8) or 80
        chart.update(render_chart(self._genres, width, self._artist_total))
