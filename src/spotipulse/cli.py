"""Entry point: auth check (prompting for login if needed), then the TUI."""

from __future__ import annotations

import argparse
import getpass
import sys

from spotipy.oauth2 import SpotifyOauthError

from . import __version__
from .config import ConfigError, config_path, load_config, save_config

GREEN = "\033[38;2;30;215;96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def _say(message: str, style: str = "") -> None:
    print(f"{style}{message}{RESET}" if style and sys.stdout.isatty() else message)


def _ask_yes(question: str) -> bool:
    try:
        answer = input(f"{question} [Y/n] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer in ("", "y", "yes")


def _ask_credentials():
    _say("\nFirst time here: spotipulse needs your Spotify app credentials.", BOLD)
    _say(
        "Create an app at https://developer.spotify.com/dashboard with the redirect URI\n"
        "  http://127.0.0.1:8888/callback\n"
        "then copy its Client ID and Client Secret below.\n",
        DIM,
    )
    try:
        client_id = input("Client ID: ").strip()
        # stdin isn't a terminal (piped): getpass would read from the console instead, so use input
        ask_secret = getpass.getpass if sys.stdin.isatty() else input
        client_secret = ask_secret("Client Secret (hidden): ").strip() if client_id else ""
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    if not client_id or not client_secret:
        _say("Both values are required. Nothing was saved.")
        return None
    config = save_config(client_id, client_secret)
    _say(f"Saved to {config_path()}", DIM)
    return config


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="spotipulse",
        description="A terminal dashboard for your Spotify stats.",
    )
    parser.add_argument("--logout", action="store_true", help="forget the cached Spotify login")
    parser.add_argument("--no-splash", action="store_true", help="skip the startup logo")
    parser.add_argument("--version", action="version", version=f"spotipulse {__version__}")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    from .auth import TokenStatus, check_token, login, logout, make_oauth

    if args.logout:
        _say("Logged out of Spotify." if logout() else "You weren't logged in.")
        return 0

    try:
        config = load_config()
    except ConfigError as exc:
        _say(f"Config problem: {exc}")
        _say(f"Fix or delete {config_path()} and run spotipulse again.")
        return 1

    status = check_token(make_oauth(config)) if config else TokenStatus.MISSING
    if status is not TokenStatus.VALID:
        if status is TokenStatus.EXPIRED:
            _say("Your Spotify login has expired (Spotify logins last 6 months).", BOLD)
        else:
            _say("Not connected to Spotify.", BOLD)
        if not _ask_yes("Open the browser to log in now?"):
            _say("No problem, run spotipulse again whenever you're ready.")
            return 0
        if config is None:
            config = _ask_credentials()
            if config is None:
                return 1
        oauth = make_oauth(config)
        _say("Opening Spotify in your browser... waiting for you to approve.", GREEN)
        _say(f"If nothing opens, go to:\n  {oauth.get_authorize_url()}", DIM)
        try:
            login(oauth)
        except SpotifyOauthError as exc:
            _say(f"Login failed: {exc}")
            _say("Check your Client ID/Secret and that the redirect URI matches exactly.")
            return 1
        except OSError as exc:
            _say(f"Couldn't start the local login server on {config.redirect_uri}: {exc}")
            return 1
        except KeyboardInterrupt:
            _say("\nLogin cancelled.")
            return 1
        _say("Connected!", GREEN)

    # Heavy imports only once we know we're launching the TUI.
    from .api import SpotifyAPI
    from .app import SpotipulseApp
    from .config import db_path
    from .db import HistoryDB

    db = HistoryDB(db_path())
    try:
        app = SpotipulseApp(SpotifyAPI.from_oauth(make_oauth(config)), db, config, splash=not args.no_splash)
        app.run()
    finally:
        db.close()
    if app.logged_out:
        _say("Logged out of Spotify. Run spotipulse to sign in again.")
    return app.return_code or 0


if __name__ == "__main__":
    sys.exit(main())
