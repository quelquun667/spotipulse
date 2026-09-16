"""Reads and creates ~/.config/spotipulse/config.toml."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_REDIRECT_URI = "http://127.0.0.1:8888/callback"
DEFAULT_REFRESH_INTERVAL = 3.0


def config_dir() -> Path:
    """Directory holding config, token cache and local history.

    `SPOTIPULSE_HOME` overrides the default location (handy for tests).
    """
    override = os.environ.get("SPOTIPULSE_HOME")
    return Path(override).expanduser() if override else Path.home() / ".config" / "spotipulse"


def config_path() -> Path:
    return config_dir() / "config.toml"


def token_cache_path() -> Path:
    return config_dir() / "token_cache"


def db_path() -> Path:
    return config_dir() / "history.db"


class ConfigError(Exception):
    """The config file exists but can't be used."""


@dataclass(frozen=True)
class Config:
    client_id: str
    client_secret: str
    redirect_uri: str = DEFAULT_REDIRECT_URI
    refresh_interval: float = DEFAULT_REFRESH_INTERVAL
    export_dir: Path | None = None

    def resolved_export_dir(self) -> Path:
        if self.export_dir:
            return self.export_dir
        pictures = Path.home() / "Pictures"
        return pictures if pictures.is_dir() else Path.home()


def load_config(path: Path | None = None) -> Config | None:
    """Return the config, or None if it doesn't exist yet."""
    path = path or config_path()
    if not path.is_file():
        return None
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path} is not valid TOML: {exc}") from exc

    spotify = data.get("spotify", {})
    app = data.get("app", {})
    client_id = str(spotify.get("client_id", "")).strip()
    client_secret = str(spotify.get("client_secret", "")).strip()
    if not client_id or not client_secret:
        return None

    try:
        refresh = float(app.get("refresh_interval", DEFAULT_REFRESH_INTERVAL))
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{path}: app.refresh_interval must be a number") from exc

    export_dir = app.get("export_dir")
    return Config(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=str(spotify.get("redirect_uri", DEFAULT_REDIRECT_URI)).strip() or DEFAULT_REDIRECT_URI,
        refresh_interval=max(1.0, refresh),
        export_dir=Path(export_dir).expanduser() if export_dir else None,
    )


def _toml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def save_config(client_id: str, client_secret: str, path: Path | None = None) -> Config:
    """Write a fresh config file with the given credentials."""
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (
        "# spotipulse configuration — keep this file private.\n\n"
        "[spotify]\n"
        f"client_id = {_toml_string(client_id.strip())}\n"
        f"client_secret = {_toml_string(client_secret.strip())}\n"
        f"redirect_uri = {_toml_string(DEFAULT_REDIRECT_URI)}\n\n"
        "[app]\n"
        f"refresh_interval = {int(DEFAULT_REFRESH_INTERVAL)}\n"
    )
    path.write_text(content, encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    config = load_config(path)
    assert config is not None
    return config
