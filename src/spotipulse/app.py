"""Main Textual app: theme, tab routing, splash, shared data cache."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.reactive import reactive
from textual.screen import Screen
from textual.theme import Theme
from textual.widgets import Footer, Header, Static, TabbedContent, TabPane

from . import asset_path
from .api import PERIOD_DAYS, TIME_RANGES, Artist, SpotifyAPI, SpotifyAPIError, Track
from .config import Config
from .db import HistoryDB
from .genres import GenreCount, fill_missing_genres, top_genres
from .stats import format_duration, listened_ms
from .widgets.genres import GenresView
from .widgets.history import HistoryView
from .widgets.now_playing import NowPlayingView
from .widgets.profile import ProfileView
from .widgets.recent import RecentView
from .widgets.top_stats import TopStatsView

SPOTIPULSE_THEME = Theme(
    name="spotipulse",
    primary="#1DB954",
    secondary="#1ED760",
    accent="#1ED760",
    foreground="#EDEDED",
    background="#121212",
    surface="#181818",
    panel="#282828",
    success="#1DB954",
    warning="#F0B429",
    error="#E5534B",
    dark=True,
)


@dataclass(frozen=True)
class TopData:
    tracks: list[Track]  # up to 50
    artists: list[Artist]  # up to 50, so genres have more to work with
    genres: list[GenreCount]


class SplashScreen(Screen):
    """The logo in block art, shown briefly on startup. Any key skips it."""

    def compose(self) -> ComposeResult:
        logo_file = asset_path("logo_ascii.txt")
        logo = logo_file.read_text(encoding="utf-8") if logo_file else ""
        with Vertical(id="splash"):
            yield Static(logo.rstrip("\n"), id="splash-logo")
            yield Static("spotipulse", id="splash-name")
            yield Static("your Spotify stats, in the terminal", id="splash-tagline")

    def on_mount(self) -> None:
        self.set_timer(1.4, self._close)

    def on_key(self) -> None:
        self._close()

    def on_click(self) -> None:
        self._close()

    def _close(self) -> None:
        if self.app.screen is self:
            self.app.pop_screen()


class SpotipulseApp(App):
    TITLE = "spotipulse"
    CSS_PATH = "theme.tcss"
    ENABLE_COMMAND_PALETTE = False

    BINDINGS = [
        # Digits, plus the unshifted AZERTY top row (& é " ' ( -) so French keyboards don't need Shift.
        Binding("1,ampersand", "show_tab('now')", "Now", key_display="1"),
        Binding("2,é", "show_tab('top')", "Top", key_display="2"),
        Binding("3,quotation_mark", "show_tab('genres')", "Genres", key_display="3"),
        Binding("4,apostrophe", "show_tab('history')", "History", key_display="4"),
        Binding("5,left_parenthesis", "show_tab('recent')", "Recent", key_display="5"),
        Binding("6,minus", "show_tab('profile')", "Profile", key_display="6"),
        Binding("slash", "filter", "Filter", show=False),
        Binding("w", "set_period('short_term')", "4 Weeks", show=False),
        Binding("m", "set_period('medium_term')", "6 Months", show=False),
        Binding("y", "set_period('long_term')", "1 Year", show=False),
        Binding("r", "refresh", "Refresh"),
        Binding("e", "export", "Export"),
        Binding("L", "logout", "Log out", show=False),
        Binding("q", "quit", "Quit"),
    ]

    period: reactive[str] = reactive("short_term")

    def __init__(self, api: SpotifyAPI, db: HistoryDB, config: Config, splash: bool = True) -> None:
        super().__init__()
        self.api = api
        self.db = db
        self.config = config
        self.splash = splash
        self.logged_out = False
        self._top_cache: dict[str, TopData] = {}
        self._top_lock = threading.Lock()

    def compose(self) -> ComposeResult:
        yield Header(icon="♪")
        with TabbedContent(initial="now", id="tabs"):
            with TabPane("Now Playing", id="now"):
                yield NowPlayingView()
            with TabPane("Top", id="top"):
                yield TopStatsView()
            with TabPane("Genres", id="genres"):
                yield GenresView()
            with TabPane("History", id="history"):
                yield HistoryView()
            with TabPane("Recently Played", id="recent"):
                yield RecentView()
            with TabPane("Profile", id="profile"):
                yield ProfileView()
        yield Footer()

    def on_mount(self) -> None:
        self.register_theme(SPOTIPULSE_THEME)
        self.theme = "spotipulse"
        if self.splash:
            self.push_screen(SplashScreen())

    # ---------- shared data ----------

    def get_top(self, time_range: str) -> TopData:
        """Blocking: call from a worker thread. Cached per period until refresh."""
        with self._top_lock:
            cached = self._top_cache.get(time_range)
            if cached:
                return cached
            tracks = self.api.top_tracks(time_range, limit=50)
            artists = fill_missing_genres(self.api.top_artists(time_range, limit=50), self.api.artist)
            data = TopData(tracks, artists, top_genres(artists))
            self._top_cache[time_range] = data
            return data

    def listening_summary(self, time_range: str) -> tuple[str | None, str]:
        """(short label for the recap card, longer line for the Top tab header)."""
        days = self.db.daily_totals()
        today = date.today()
        length = PERIOD_DAYS[time_range]
        start = today - timedelta(days=length - 1)
        ms, plays = listened_ms(days, start, today)
        if not plays:
            return (
                None,
                "No local history for this period yet — spotipulse logs what you play while it's open.",
            )
        first = self.db.first_play()
        since = ""
        if first and first.astimezone().date() > start:
            since = f" (tracked since {first.astimezone():%b %d})"
        label = f"≈ {format_duration(ms)} listened"
        period = TIME_RANGES[time_range].lower()
        plays_label = f"{plays} play{'s' if plays != 1 else ''}"
        return label, f"[b]{label}[/b] in the last {period}{since} · {plays_label}"

    # ---------- actions ----------

    def action_show_tab(self, tab: str) -> None:
        self.query_one("#tabs", TabbedContent).active = tab
        # Put the keyboard on the tab's main table so arrows work straight away.
        table_id = {"top": "#top-tracks", "recent": "#recent-table"}.get(tab)
        if table_id:
            self.call_after_refresh(lambda: self.query_one(table_id).focus())

    def action_filter(self) -> None:
        self.action_show_tab("top")
        self.call_after_refresh(self.query_one(TopStatsView).action_focus_filter)

    def action_set_period(self, time_range: str) -> None:
        self.period = time_range

    def watch_period(self, time_range: str) -> None:
        for view in self.query(TopStatsView):
            view.period_changed(time_range)
        for view in self.query(GenresView):
            view.period_changed(time_range)

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        self._activate(event.pane.id)

    def _activate(self, pane_id: str | None) -> None:
        views = {
            "top": TopStatsView,
            "genres": GenresView,
            "history": HistoryView,
            "recent": RecentView,
            "profile": ProfileView,
        }
        if pane_id in views:
            self.query_one(views[pane_id]).activate()

    def action_refresh(self) -> None:
        with self._top_lock:
            self._top_cache.clear()
        self.query_one(NowPlayingView).poll()
        for view_type in (TopStatsView, GenresView, HistoryView, RecentView, ProfileView):
            self.query_one(view_type).stale = True
        self._activate(self.query_one("#tabs", TabbedContent).active)
        self.notify("Refreshing…", timeout=1.5)

    @work(thread=True, exclusive=True, group="export")
    def action_export(self) -> None:
        time_range = self.period
        self.call_from_thread(self.notify, f"Building your {TIME_RANGES[time_range]} recap…", timeout=2)
        try:
            data = self.get_top(time_range)
        except SpotifyAPIError as exc:
            self.call_from_thread(self.notify, str(exc), severity="error")
            return
        from .export import render_recap

        label, _ = self.listening_summary(time_range)
        try:
            path = render_recap(
                data.tracks,
                data.artists,
                data.genres,
                TIME_RANGES[time_range],
                label,
                self.config.resolved_export_dir(),
                now=datetime.now(),
            )
        except OSError as exc:
            self.call_from_thread(self.notify, f"Couldn't save the recap: {exc}", severity="error")
            return
        self.call_from_thread(self.notify, f"Recap saved to {path}", title="Exported", timeout=8)

    def action_logout(self) -> None:
        from .auth import logout

        logout()
        self.logged_out = True
        self.exit()
