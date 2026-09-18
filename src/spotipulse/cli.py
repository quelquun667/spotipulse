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


CONFIG_HELP = """\
settings:
  spotipulse config               list every setting with its value
  spotipulse config set KEY VALUE change one        (e.g. spotipulse config set theme light)
  spotipulse config get KEY       print one value
  spotipulse config reset KEY     back to the default
  spotipulse config edit          open the file in your editor (same as --config)
  spotipulse config path          print where the file is
"""


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="spotipulse",
        description="A terminal dashboard for your Spotify stats.",
        epilog=CONFIG_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--logout", action="store_true", help="forget the cached Spotify login")
    parser.add_argument("--no-splash", action="store_true", help="skip the startup logo")
    parser.add_argument("--mini", action="store_true", help="start in the compact view (press c to toggle)")
    parser.add_argument("--config", action="store_true", help="open the settings file in your editor")
    parser.add_argument(
        "--demo", action="store_true", help="try the dashboard on made-up data (no Spotify account needed)"
    )
    parser.add_argument("--version", action="version", version=f"spotipulse {__version__}")
    commands = parser.add_subparsers(dest="command", title="commands", metavar="COMMAND")
    config = commands.add_parser(
        "config",
        help="list or change settings (see below)",
        description="Read and change spotipulse settings.",
        epilog=CONFIG_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    config.add_argument("action", nargs="?", choices=("list", "get", "set", "reset", "edit", "path"))
    config.add_argument("key", nargs="?", help="setting name, e.g. theme")
    config.add_argument("value", nargs="?", help="new value, for set")
    return parser.parse_args(argv)


def _run_demo(args: argparse.Namespace) -> int:
    """The dashboard on made-up data: no login, nothing sent to Spotify, history kept in memory."""
    from dataclasses import replace

    from .app import SpotipulseApp
    from .config import Config, effective_config
    from .demo import DemoAPI, demo_history

    try:
        config = replace(effective_config(), client_id="demo", client_secret="demo")
    except ConfigError:
        config = Config("demo", "demo")
    app = SpotipulseApp(DemoAPI(), demo_history(), config, splash=not args.no_splash, mini=args.mini)
    app.sub_title = "demo mode · everything here is made up"
    app.run()
    return app.return_code or 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    if args.config or args.command == "config":
        from . import config_cli

        action = "edit" if args.config else args.action
        return config_cli.run(action, getattr(args, "key", None), getattr(args, "value", None))

    if args.demo:
        return _run_demo(args)

    from .auth import TokenStatus, check_token, login, logout, make_oauth

    if args.logout:
        _say("Logged out of Spotify." if logout() else "You weren't logged in.")
        return 0

    try:
        config = load_config()
    except ConfigError as exc:
        _say(f"Config problem: {exc}")
        _say("Fix it with `spotipulse --config`, or reset a setting with `spotipulse config reset <name>`.")
        return 1

    status = check_token(make_oauth(config)) if config else TokenStatus.MISSING
    if status is not TokenStatus.VALID:
        if status is TokenStatus.EXPIRED:
            _say("Your Spotify login has expired (Spotify logins last 6 months).", BOLD)
        elif status is TokenStatus.NEEDS_CONSENT:
            _say("spotipulse needs a few more Spotify permissions (for the Profile tab).", BOLD)
            _say("Log in once more to approve them.", DIM)
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
            if getattr(exc, "error", None) in ("server_error", "access_denied"):
                _say(
                    "Spotify refused this account for your app. Development Mode apps need:\n"
                    "  - a Spotify Premium subscription on the account that owns the app\n"
                    "  - the account you log in with added under User Management in the dashboard\n"
                    "  - to be logged into that same account in your browser"
                )
            else:
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
    from .cache import DiskCache
    from .config import cache_dir, db_path
    from .db import HistoryDB

    db = HistoryDB(db_path())
    disk = DiskCache(cache_dir())
    try:
        app = SpotipulseApp(
            SpotifyAPI.from_oauth(make_oauth(config), disk=disk),
            db,
            config,
            splash=not args.no_splash,
            disk=disk,
            mini=args.mini,
        )
        app.run()
    finally:
        db.close()
    if app.logged_out:
        _say("Logged out of Spotify. Run spotipulse to sign in again.")
    return app.return_code or 0


if __name__ == "__main__":
    sys.exit(main())
