"""Local listening history: day-by-day graph, streaks, period comparison."""

from __future__ import annotations

from datetime import date

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import DataTable, Static

from ..db import DayTotal
from ..stats import (
    Comparison,
    compare_periods,
    current_streak,
    daily_series,
    format_change,
    format_duration,
    longest_streak,
)
from . import LazyView

CHART_DAYS = 30
CHART_HEIGHT = 8
EIGHTHS = " ▁▂▃▄▅▆▇█"


def render_daily_chart(series: list[DayTotal], width: int) -> Text:
    """Vertical bars of minutes listened per day, oldest on the left."""
    text = Text()
    peak = max((d.ms for d in series), default=0)
    if peak == 0:
        text.append("No plays logged in the last 30 days.", style="italic dim")
        return text
    axis_width = 7
    column = max(1, min(4, (width - axis_width) // len(series)))
    bar = max(1, column - 1)
    levels = [d.ms / peak * CHART_HEIGHT * 8 for d in series]  # in eighths of a row
    for row in range(CHART_HEIGHT, 0, -1):
        if row == CHART_HEIGHT:
            text.append(f"{format_duration(peak):>6} ", style="dim")
        elif row == 1:
            text.append(f"{'0m':>6} ", style="dim")
        else:
            text.append(" " * axis_width)
        for i, level in enumerate(levels):
            filled = level - (row - 1) * 8
            char = "█" if filled >= 8 else EIGHTHS[max(0, int(filled))]
            style = "bold #1ED760" if i == len(levels) - 1 else "#1DB954"
            text.append(char * bar, style=style)
            text.append(" " * (column - bar))
        text.append("\n")
    # date labels under the first, middle and last bars
    labels = [" "] * (len(series) * column)
    for index in (0, len(series) // 2, len(series) - 1):
        label = f"{series[index].day:%b %d}"
        start = min(index * column, len(labels) - len(label))
        labels[start : start + len(label)] = label
    text.append(" " * axis_width + "".join(labels).rstrip(), style="dim")
    return text


class HistoryView(LazyView):
    def __init__(self) -> None:
        super().__init__()
        self._series: list[DayTotal] = []

    def compose(self) -> ComposeResult:
        with Horizontal(id="history-cards"):
            yield Static("", id="card-plays", classes="card")
            yield Static("", id="card-time", classes="card")
            yield Static("", id="card-streak", classes="card")
            yield Static("", id="card-best", classes="card")
        chart = Static("", id="history-chart", classes="panel")
        chart.border_title = f"Last {CHART_DAYS} days"
        yield chart
        yield DataTable(id="history-compare", cursor_type="none", show_cursor=False)
        yield Static("", id="history-note", classes="muted")

    def on_mount(self) -> None:
        table = self.query_one("#history-compare", DataTable)
        table.add_column("Period", key="period")
        table.add_column("Listening", key="listening")
        table.add_column("Plays", key="plays")
        table.add_column("Previous", key="previous")
        table.add_column("Change", key="change")

    def activate(self) -> None:
        # Local data changes while the app runs, so always reload: it's a cheap SQLite query.
        self.load()

    def load(self) -> None:
        self._fetch()

    @work(thread=True, exclusive=True, group="history")
    def _fetch(self) -> None:
        db = self.app.db
        days = db.daily_totals()
        first = db.first_play()
        self.app.call_from_thread(self._loaded, days, db.play_count(), first)

    def _loaded(self, days: list[DayTotal], total_plays: int, first) -> None:
        today = date.today()
        active = [d.day for d in days if d.plays]
        total_ms = sum(d.ms for d in days)
        streak = current_streak(active, today)
        self.query_one("#card-plays", Static).update(f"[dim]Plays logged[/dim]\n[b $primary]{total_plays}[/]")
        since = f"since {first.astimezone():%b %d}" if first else "nothing yet"
        self.query_one("#card-time", Static).update(
            f"[dim]Time listened · {since}[/dim]\n[b $primary]≈ {format_duration(total_ms)}[/]"
        )
        self.query_one("#card-streak", Static).update(
            f"[dim]Current streak[/dim]\n[b $primary]{streak} day{'s' if streak != 1 else ''}[/]"
        )
        best = longest_streak(active)
        self.query_one("#card-best", Static).update(
            f"[dim]Longest streak[/dim]\n[b $primary]{best} day{'s' if best != 1 else ''}[/]"
        )

        self._series = daily_series(days, CHART_DAYS, today)
        self._redraw()

        table = self.query_one("#history-compare", DataTable)
        table.clear()
        comparisons: list[Comparison] = [
            compare_periods(days, today, 7, "Last 7 days"),
            compare_periods(days, today, 30, "Last 30 days"),
        ]
        for c in comparisons:
            change = format_change(c.change_pct)
            style = "#1ED760" if (c.change_pct or 0) > 0 else "#E5534B" if (c.change_pct or 0) < 0 else "dim"
            table.add_row(
                c.label,
                format_duration(c.current_ms),
                str(c.current_plays),
                format_duration(c.previous_ms),
                Text(change, style=style),
            )

        note = self.query_one("#history-note", Static)
        if total_plays:
            note.update("Tracks are logged while spotipulse is open (after 30 s of listening).")
        else:
            note.update(
                "No local history yet. spotipulse logs each track you listen to while it's open — "
                "leave it running on the Now Playing tab and this fills up."
            )

    def on_resize(self) -> None:
        self._redraw()

    def _redraw(self) -> None:
        if not self._series:
            return
        chart = self.query_one("#history-chart", Static)
        width = chart.content_region.width or 80
        chart.update(render_daily_chart(self._series, width))
