"""Your Spotify profile: avatar, library counts, favorites and playlists."""

from __future__ import annotations

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.markup import escape
from textual.widgets import DataTable, Static

from ..api import Profile, SpotifyAPIError
from ..cache import decode_profile, encode_profile
from . import CoverArt, LazyView, fit_columns, placeholder_cover


def count_label(value: int | None) -> str:
    return f"{value:,}".replace(",", " ") if value is not None else "—"


PLAYLIST_COLUMNS = [("name", "Playlist", 12, 3), ("tracks", "Tracks", 6, 0), ("owner", "Owner", 8, 1)]


class ProfileView(LazyView):
    def __init__(self) -> None:
        super().__init__()
        self._profile: Profile | None = None
        self._shown_cached = False

    def compose(self) -> ComposeResult:
        with Horizontal(id="profile-header"):
            yield CoverArt(placeholder_cover(), id="profile-avatar")
            with Vertical(id="profile-identity"):
                yield Static("Loading…", id="profile-name")
                yield Static("", id="profile-link")
                with Horizontal(id="profile-cards"):
                    yield Static("", id="card-liked", classes="card")
                    yield Static("", id="card-albums", classes="card")
                    yield Static("", id="card-playlists", classes="card")
                    yield Static("", id="card-following", classes="card")
        with Horizontal(id="profile-body"):
            favorites = Static("", id="profile-favorites", classes="panel")
            favorites.border_title = "Favorites"
            yield favorites
            with Vertical(id="profile-playlists-panel", classes="panel") as panel:
                panel.border_title = "Your playlists"
                yield DataTable(id="profile-playlists", cursor_type="row")

    def on_mount(self) -> None:
        self.call_after_refresh(self._fit_columns)

    def on_resize(self) -> None:
        self.call_after_refresh(self._fit_columns)

    def _fit_columns(self) -> None:
        if fit_columns(self.query_one("#profile-playlists", DataTable), PLAYLIST_COLUMNS):
            self._render_playlists()

    def load(self) -> None:
        self._fetch()

    @work(thread=True, exclusive=True, group="profile")
    def _fetch(self) -> None:
        app = self.app
        if app.disk and not self._shown_cached:
            self._shown_cached = True
            hit = app.disk.load_decoded("profile", decode_profile)
            if hit:
                self._show(hit[0])
        try:
            profile = app.api.profile()
        except SpotifyAPIError as exc:
            app.call_from_thread(self._failed, str(exc))
            return
        if app.disk:
            app.disk.save("profile", encode_profile(profile))
        self._show(profile)

    def _show(self, profile: Profile) -> None:
        """Worker thread: gather the avatar and favorites, then update the UI."""
        app = self.app
        avatar = app.api.image(profile.image_url) or placeholder_cover()
        favorites = []
        for time_range, label in (("short_term", "Last 4 weeks"), ("long_term", "Last year")):
            try:
                top = app.get_top(time_range)
            except SpotifyAPIError:
                continue
            favorites.append((label, top))
        app.call_from_thread(self._loaded, profile, avatar, favorites)

    def _failed(self, message: str) -> None:
        self.stale = True
        self.query_one("#profile-name", Static).update(f"[red]{escape(message)}[/red]")

    def _loaded(self, profile: Profile, avatar, favorites) -> None:
        self.query_one("#profile-avatar", CoverArt).image = avatar
        self.query_one("#profile-name", Static).update(f"[b]{escape(profile.display_name)}[/b]")
        self.query_one("#profile-link", Static).update(f"[dim]{escape(profile.url or '')}[/dim]")
        cards = (
            ("#card-liked", "Liked songs", profile.liked_tracks),
            ("#card-albums", "Saved albums", profile.saved_albums),
            ("#card-playlists", "Playlists", profile.playlist_count),
            ("#card-following", "Artists followed", profile.followed_artists),
        )
        for widget_id, label, value in cards:
            self.query_one(widget_id, Static).update(
                f"[dim]{label}[/dim]\n[b $primary]{count_label(value)}[/]"
            )

        text = Text()
        for label, top in favorites:
            if text:
                text.append("\n\n")
            text.append(label.upper(), style="bold #1ED760")
            rows = (
                ("Top track", f"{top.tracks[0].name} — {top.tracks[0].artist_line}" if top.tracks else None),
                ("Top artist", top.artists[0].name if top.artists else None),
                ("Top genre", top.genres[0].genre.title() if top.genres else None),
            )
            for name, value in rows:
                text.append(f"\n{name:<12}", style="dim")
                text.append(value or "—", style="bold" if value else "dim")
        if not favorites:
            text.append("Couldn't load your top items.", style="italic dim")
        self.query_one("#profile-favorites", Static).update(text)

        self._profile = profile
        self._render_playlists()

    def _render_playlists(self) -> None:
        table = self.query_one("#profile-playlists", DataTable)
        profile = self._profile
        if profile is None or not table.columns:
            return
        table.clear()
        for playlist in profile.playlists:
            table.add_row(
                Text(playlist.name),
                str(playlist.tracks) if playlist.tracks is not None else "—",
                Text(playlist.owner, style="dim"),
            )
        if profile.playlist_count and profile.playlist_count > len(profile.playlists):
            extra = profile.playlist_count - len(profile.playlists)
            table.add_row(Text(f"… and {extra} more", style="dim italic"), "", "")
