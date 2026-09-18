"""Main Textual app: theme, tab routing, splash, shared data cache."""

from __future__ import annotations

import contextlib
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

from . import asset_path, palette
from .api import PERIOD_DAYS, TIME_RANGES, Artist, SpotifyAPI, SpotifyAPIError, Track
from .cache import DiskCache, decode_top, encode_top
from .config import Config
from .db import HistoryDB
from .genres import GenreCount, fill_missing_genres, top_genres
from .stats import format_duration, listened_ms
from .widgets import set_cover_mode
from .widgets.export_menu import ExportScreen
from .widgets.genres import GenresView
from .widgets.help import HelpScreen
from .widgets.history import HistoryView
from .widgets.mini import MiniScreen
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

SPOTIPULSE_LIGHT_THEME = Theme(
    name="spotipulse-light",
    primary="#138A43",
    secondary="#1DB954",
    accent="#138A43",
    foreground="#1A1A1A",
    background="#F4F4F4",
    surface="#FFFFFF",
    panel="#D9D9D9",
    success="#138A43",
    warning="#B7791F",
    error="#C62828",
    dark=False,
)
THEME_NAMES = {"dark": "spotipulse", "light": "spotipulse-light"}


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
        self.set_timer(0.8, self._close)

    def on_key(self) -> None:
        self._close()

    def on_click(self) -> None:
        self._close()

    def _close(self) -> None:
        if self.app.screen is self:
            self.app.pop_screen()
            self.app.action_redraw()


class SpotipulseApp(App):
    TITLE = "spotipulse"
    CSS_PATH = "theme.tcss"
    ENABLE_COMMAND_PALETTE = False
    # Responsive layout: these classes land on the screen, theme.tcss adapts the panels to them.
    HORIZONTAL_BREAKPOINTS = [(0, "-narrow"), (100, "-medium"), (140, "-wide")]
    VERTICAL_BREAKPOINTS = [(0, "-short"), (36, "-tall")]

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
        Binding("c", "toggle_mini", "Compact"),
        Binding("ctrl+l", "redraw", "Redraw", show=False),
        # "comma" is where ? sits on an AZERTY keyboard, so no Shift needed there either.
        Binding("question_mark,comma,f1", "toggle_help", "Help", key_display="?"),
        Binding("r", "refresh", "Refresh"),
        Binding("e", "export", "Export"),
        Binding("E", "choose_export", "Export as…", show=False),
        Binding("t", "toggle_theme", "Theme", show=False),
        Binding("L", "logout", "Log out", show=False),
        Binding("q", "quit", "Quit"),
    ]

    period: reactive[str] = reactive("short_term")

    def __init__(
        self,
        api: SpotifyAPI,
        db: HistoryDB,
        config: Config,
        splash: bool = True,
        disk: DiskCache | None = None,
        mini: bool = False,
    ) -> None:
        super().__init__()
        self.api = api
        self.db = db
        self.config = config
        self.splash = splash and not mini
        self.start_mini = mini
        self.disk = disk
        self.logged_out = False
        # Before compose(): the cover widgets are built there, so the mode has to be set first.
        set_cover_mode(config.covers)
        palette.set_dark(config.theme == "dark")
        if not config.animations:
            self.animation_level = "none"
        self._top_cache: dict[str, TopData] = {}
        self._top_lock = threading.Lock()
        # Periods already fetched live this session: the disk cache is only a startup shortcut.
        self._live_top: set[str] = set()

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
        self.register_theme(SPOTIPULSE_LIGHT_THEME)
        self.theme = THEME_NAMES[self.config.theme]
        if self.start_mini:
            self.push_screen(MiniScreen())
        elif self.splash:
            self.push_screen(SplashScreen())

    # ---------- shared data ----------

    def get_top(self, time_range: str) -> TopData:
        """Blocking: call from a worker thread. Cached per period until refresh.

        On the first call of a session, the last saved copy is returned straight away (if any)
        and fresh data is fetched in the background; views are told to redraw once it lands.
        """
        with self._top_lock:
            cached = self._top_cache.get(time_range)
            if cached:
                return cached
            if self.disk and time_range not in self._live_top:
                hit = self.disk.load_decoded(f"top_{time_range}", decode_top)
                if hit:
                    data = TopData(*hit[0])
                    self._top_cache[time_range] = data
                    self._live_top.add(time_range)
                    threading.Thread(target=self._refresh_top, args=(time_range,), daemon=True).start()
                    return data
            return self._fetch_top(time_range)

    def _fetch_top(self, time_range: str) -> TopData:
        """Fetch from Spotify and store in memory + on disk. Caller holds `_top_lock`."""
        tracks = self.api.top_tracks(time_range, limit=50)
        artists = fill_missing_genres(self.api.top_artists(time_range, limit=50), self.api.artist)
        data = TopData(tracks, artists, top_genres(artists))
        self._top_cache[time_range] = data
        self._live_top.add(time_range)
        if self.disk:
            self.disk.save(f"top_{time_range}", encode_top(data.tracks, data.artists, data.genres))
        return data

    def _refresh_top(self, time_range: str) -> None:
        try:
            with self._top_lock:
                self._fetch_top(time_range)
        except SpotifyAPIError:
            return  # keep showing the cached copy
        with contextlib.suppress(RuntimeError):  # the app may have exited meanwhile
            self.call_from_thread(self._top_refreshed)

    def _top_refreshed(self) -> None:
        for view_type in (TopStatsView, GenresView, ProfileView):
            for view in self.query(view_type):
                view.stale = True
        self._activate(self._main_tabs().active)

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

    def _main_tabs(self) -> TabbedContent:
        return self.query_one("#tabs", TabbedContent)

    def _close_overlays(self) -> None:
        """Back to the dashboard from the compact view or the help overlay."""
        closed = False
        while len(self.screen_stack) > 1 and isinstance(self.screen, (MiniScreen, HelpScreen, SplashScreen)):
            self.pop_screen()
            closed = True
        if closed:
            self.action_redraw()

    def action_redraw(self) -> None:
        """Repaint every cell.

        Textual only redraws what changed, so terminals drawing cover art with their image protocol can
        leave a stale line behind when a screen closes. Marking everything dirty wipes it.
        """
        self.refresh(layout=True)
        for widget in self.screen.walk_children():
            widget.refresh()

    def action_toggle_mini(self) -> None:
        if isinstance(self.screen, MiniScreen):
            self.pop_screen()
            self.action_redraw()
        else:
            self._close_overlays()
            self.push_screen(MiniScreen())

    def action_toggle_help(self) -> None:
        if isinstance(self.screen, HelpScreen):
            self.pop_screen()
            self.action_redraw()
        else:
            self.push_screen(HelpScreen())

    def action_show_tab(self, tab: str) -> None:
        self._close_overlays()
        self._main_tabs().active = tab
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
        self.fade_in(event.pane)
        self._activate(event.pane.id)

    def fade_in(self, widget, duration: float = 0.15) -> None:
        """Quick fade of a view's text when it appears (skipped when `animations = false`).

        Fades `text_opacity` rather than `opacity`: animating a whole panel's opacity leaves Textual
        painting the screen background behind its text afterwards.
        """
        if not self.config.animations:
            return
        widget.styles.text_opacity = 0.0
        widget.styles.animate(
            "text_opacity",
            1.0,
            duration=duration,
            on_complete=lambda: widget.styles.clear_rule("text_opacity"),
        )

    def action_toggle_theme(self) -> None:
        dark = not self.current_theme.dark
        self.theme = THEME_NAMES["dark" if dark else "light"]
        palette.set_dark(dark)
        # Text built in Python (tables, charts) holds its colors: rebuild the views.
        self.query_one(NowPlayingView).poll()
        for view_type in (TopStatsView, GenresView, HistoryView, RecentView, ProfileView):
            self.query_one(view_type).stale = True
        self._activate(self._main_tabs().active)
        self.notify(f"{'Dark' if dark else 'Light'} theme", timeout=1.5)

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
            self._live_top.update(TIME_RANGES)
        self.query_one(NowPlayingView).poll()
        for view_type in (TopStatsView, GenresView, HistoryView, RecentView, ProfileView):
            self.query_one(view_type).stale = True
        self._activate(self._main_tabs().active)
        self.notify("Refreshing…", timeout=1.5)

    def action_choose_export(self) -> None:
        def chosen(fmt: str | None) -> None:
            if fmt:
                self.action_export(fmt)

        self.push_screen(ExportScreen(default=self.config.recap_format), chosen)

    @work(thread=True, exclusive=True, group="export")
    def action_export(self, fmt: str | None = None) -> None:
        time_range = self.period
        fmt = fmt or self.config.recap_format
        self.call_from_thread(
            self.notify, f"Building your {TIME_RANGES[time_range]} recap ({fmt})…", timeout=2
        )
        try:
            data = self.get_top(time_range)
        except SpotifyAPIError as exc:
            self.call_from_thread(self.notify, str(exc), severity="error")
            return
        from .export import render_recap

        label, _ = self.listening_summary(time_range)
        user_name, avatar_url = self._profile_brief()
        try:
            path = render_recap(
                data.tracks,
                data.artists,
                data.genres,
                TIME_RANGES[time_range],
                label,
                self.config.resolved_export_dir(),
                now=datetime.now(),
                images=self.api.image,
                user_name=user_name,
                avatar_url=avatar_url,
                fmt=fmt,
            )
        except OSError as exc:
            self.call_from_thread(self.notify, f"Couldn't save the recap: {exc}", severity="error")
            return
        self.call_from_thread(self.notify, f"Recap saved to {path}", title="Exported", timeout=8)

    def _profile_brief(self) -> tuple[str | None, str | None]:
        """Blocking. (name, avatar URL): the Profile tab's cached copy if there is one, else ask Spotify."""
        if self.disk:
            from .cache import decode_profile

            hit = self.disk.load_decoded("profile", decode_profile)
            if hit:
                return hit[0].display_name, hit[0].image_url
        try:
            return self.api.me_brief()
        except SpotifyAPIError:
            return None, None

    def action_logout(self) -> None:
        from .auth import logout

        logout()
        self.logged_out = True
        self.exit()
