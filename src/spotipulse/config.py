"""Reads and creates ~/.config/spotipulse/config.toml."""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path

DEFAULT_REDIRECT_URI = "http://127.0.0.1:8888/callback"
DEFAULT_REFRESH_INTERVAL = 3.0
# "auto" uses the terminal's image protocol (Sixel / Kitty) for real cover art. Some terminals redraw
# it badly (leftovers on screen, flicker while selecting text) -- "blocks" is the safe fallback.
DEFAULT_COVERS = "auto"
COVER_MODES = ("blocks", "auto", "unicode", "off")
# Recap card sizes: feed 1080x1350 (4:5), story 1080x1920 (9:16), square 1080x1080.
DEFAULT_RECAP_FORMAT = "feed"
RECAP_FORMATS = ("feed", "story", "square")
THEMES = ("dark", "light")


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


def cache_dir() -> Path:
    """Last-known data and downloaded covers, so the dashboard shows up instantly on launch."""
    return config_dir() / "cache"


class ConfigError(Exception):
    """The config file exists but can't be used."""


@dataclass(frozen=True)
class Config:
    client_id: str
    client_secret: str
    redirect_uri: str = DEFAULT_REDIRECT_URI
    refresh_interval: float = DEFAULT_REFRESH_INTERVAL
    export_dir: Path | None = None
    covers: str = DEFAULT_COVERS
    recap_format: str = DEFAULT_RECAP_FORMAT
    # Equalizer bars next to "Now playing" and the short fade when switching views.
    animations: bool = True
    # Tint the Now Playing tab with the current cover's main color.
    accent_from_cover: bool = False
    theme: str = "dark"

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

    covers = _choice(app, "covers", DEFAULT_COVERS, COVER_MODES, path)
    recap_format = _choice(app, "recap_format", DEFAULT_RECAP_FORMAT, RECAP_FORMATS, path)
    theme = _choice(app, "theme", "dark", THEMES, path)
    animations = _flag(app, "animations", True, path)
    accent_from_cover = _flag(app, "accent_from_cover", False, path)

    export_dir = app.get("export_dir")
    return Config(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=str(spotify.get("redirect_uri", DEFAULT_REDIRECT_URI)).strip() or DEFAULT_REDIRECT_URI,
        refresh_interval=max(1.0, refresh),
        export_dir=Path(export_dir).expanduser() if export_dir else None,
        covers=covers,
        recap_format=recap_format,
        animations=animations,
        accent_from_cover=accent_from_cover,
        theme=theme,
    )


def _choice(section: dict, key: str, default: str, allowed: tuple[str, ...], path: Path) -> str:
    value = str(section.get(key, default)).strip().lower()
    if value not in allowed:
        raise ConfigError(f"{path}: app.{key} must be one of {', '.join(allowed)} (got {value!r})")
    return value


def _flag(section: dict, key: str, default: bool, path: Path) -> bool:
    value = section.get(key, default)
    if not isinstance(value, bool):
        raise ConfigError(f"{path}: app.{key} must be true or false, without quotes (got {value!r})")
    return value


def _toml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _write_file(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    try:
        os.chmod(path, 0o600)  # the file holds the app secret
    except OSError:
        pass


def save_config(client_id: str, client_secret: str, path: Path | None = None) -> Config:
    """Store the Spotify credentials, keeping any settings already in the file."""
    path = path or config_path()
    if path.is_file():
        write_value("spotify", "client_id", client_id.strip(), path)
        write_value("spotify", "client_secret", client_secret.strip(), path)
        existing = tomllib.loads(path.read_text(encoding="utf-8")).get("spotify", {})
        if not existing.get("redirect_uri"):
            write_value("spotify", "redirect_uri", DEFAULT_REDIRECT_URI, path)
    else:
        _write_file(path, template(client_id.strip(), client_secret.strip()))
    config = load_config(path)
    assert config is not None
    return config


def template(client_id: str = "", client_secret: str = "") -> str:
    """A new config file: credentials, then every setting commented out at its default."""
    lines = [
        "# spotipulse configuration -- keep this file private (it holds your app secret).",
        "# Settings left commented out keep their default. Restart spotipulse after editing,",
        "# or change them from the app with the s key. Docs: the Settings section of the README.",
        "",
        "[spotify]",
        f"client_id = {_toml_string(client_id)}",
        f"client_secret = {_toml_string(client_secret)}",
        f"redirect_uri = {_toml_string(DEFAULT_REDIRECT_URI)}",
        "",
        "[app]",
    ]
    for setting in SETTINGS:
        lines.append("")
        lines.append(f"# {setting.description}")
        if setting.choices:
            lines.append(f"# one of: {', '.join(setting.choices)}")
        default = setting.default if setting.default is not None else "~/Pictures"
        lines.append(f"# {setting.key} = {toml_literal(default)}")
    return "\n".join(lines) + "\n"


# ---------- settings registry: shared by `spotipulse config`, the in-app Settings screen and docs ----------


@dataclass(frozen=True)
class Setting:
    key: str
    kind: str  # "choice" | "bool" | "number" | "path"
    default: object
    description: str
    choices: tuple[str, ...] = ()
    # False: takes effect the next time spotipulse starts
    live: bool = True


SETTINGS: tuple[Setting, ...] = (
    Setting("theme", "choice", "dark", "Colors of the dashboard", THEMES),
    Setting("covers", "choice", DEFAULT_COVERS, "How album art is drawn", COVER_MODES, live=False),
    Setting("accent_from_cover", "bool", False, "Tint Now Playing with the current cover's color"),
    Setting("animations", "bool", True, "Equalizer bars and fades"),
    Setting("recap_format", "choice", DEFAULT_RECAP_FORMAT, "Size of the card e exports", RECAP_FORMATS),
    Setting("export_dir", "path", None, "Folder where recap cards are saved (empty = Pictures)"),
    Setting("refresh_interval", "number", 3, "Seconds between Now Playing refreshes (1 or more)"),
)
SETTINGS_BY_KEY = {setting.key: setting for setting in SETTINGS}
_TRUE = {"true", "on", "yes", "1", "y"}
_FALSE = {"false", "off", "no", "0", "n"}


def get_setting(key: str) -> Setting:
    try:
        return SETTINGS_BY_KEY[key]
    except KeyError:
        known = ", ".join(SETTINGS_BY_KEY)
        raise ConfigError(f"unknown setting {key!r}. Settings are: {known}") from None


def parse_setting(key: str, raw: object) -> object:
    """Validate a value typed by the user; returns what goes in the file (None = back to default)."""
    setting = get_setting(key)
    if isinstance(raw, bool) and setting.kind == "bool":
        return raw
    text = str(raw).strip().strip('"').strip("'")
    if setting.kind == "choice":
        value = text.lower()
        if value not in setting.choices:
            raise ConfigError(f"{key} must be one of {', '.join(setting.choices)} (got {text!r})")
        return value
    if setting.kind == "bool":
        if text.lower() in _TRUE:
            return True
        if text.lower() in _FALSE:
            return False
        raise ConfigError(f"{key} must be true or false (got {text!r})")
    if setting.kind == "number":
        try:
            number = float(text)
        except ValueError:
            raise ConfigError(f"{key} must be a number (got {text!r})") from None
        if number < 1:
            raise ConfigError(f"{key} must be 1 or more (got {text!r})")
        return int(number) if number.is_integer() else number
    # path
    return None if text.lower() in ("", "default", "none") else text


def config_value(key: str, file_value: object) -> object:
    """Turn a file value into what `Config` holds for that field."""
    if key == "export_dir":
        return Path(str(file_value)).expanduser() if file_value else None
    if key == "refresh_interval":
        return max(1.0, float(file_value if file_value is not None else DEFAULT_REFRESH_INTERVAL))
    return file_value if file_value is not None else get_setting(key).default


def with_setting(config: Config, key: str, file_value: object) -> Config:
    return replace(config, **{key: config_value(key, file_value)})


def display_value(config: Config, key: str) -> str:
    value = getattr(config, key)
    if key == "export_dir":
        return str(value) if value else f"{config.resolved_export_dir()} (default)"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def toml_literal(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(int(value)) if float(value).is_integer() else str(value)
    return _toml_string(str(value))


_SECTION = re.compile(r"^\s*\[([^\]]+)\]\s*$")


def write_value(section: str, key: str, value: object, path: Path | None = None) -> None:
    """Set one `key = value` line, leaving the rest of the file and its comments alone.

    A commented-out `# key = ...` line is uncommented in place. `None` resets: the line goes back to a
    comment showing the default (or disappears, for keys that aren't settings).
    """
    path = path or config_path()
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    key_line = re.compile(rf"^\s*{re.escape(key)}\s*=")
    commented_line = re.compile(rf"^\s*#\s*{re.escape(key)}\s*=")
    section_at = key_at = commented_at = None
    section_end = len(lines)
    for i, line in enumerate(lines):
        header = _SECTION.match(line)
        if header:
            if section_at is not None:
                section_end = i
                break
            if header.group(1).strip() == section:
                section_at = i
            continue
        if section_at is not None and key_line.match(line):
            key_at = i
        elif section_at is not None and commented_line.match(line):
            commented_at = i
    new_line = f"{key} = {toml_literal(value)}" if value is not None else None
    setting = SETTINGS_BY_KEY.get(key) if section == "app" else None
    if key_at is not None:
        if new_line is not None:
            lines[key_at] = new_line
        elif setting is not None and commented_at is None:
            default = setting.default if setting.default is not None else "~/Pictures"
            lines[key_at] = f"# {key} = {toml_literal(default)}"
        else:
            lines.pop(key_at)
    elif new_line is not None and commented_at is not None:
        lines[commented_at] = new_line
    elif new_line is not None:
        if section_at is None:
            if lines and lines[-1].strip():
                lines.append("")
            lines += [f"[{section}]", new_line]
        else:
            insert_at = section_end
            while insert_at - 1 > section_at and not lines[insert_at - 1].strip():
                insert_at -= 1
            lines.insert(insert_at, new_line)
    _write_file(path, "\n".join(lines) + "\n")


def set_setting(key: str, raw: object, path: Path | None = None) -> object:
    """Validate and save one [app] setting. Returns the value written (None = reset to default)."""
    value = parse_setting(key, raw)
    write_value("app", key, value, path)
    return value


def read_settings(path: Path | None = None) -> dict[str, object]:
    """The [app] values actually written in the file (settings not listed use their default)."""
    path = path or config_path()
    if not path.is_file():
        return {}
    try:
        return dict(tomllib.loads(path.read_text(encoding="utf-8")).get("app", {}))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path} is not valid TOML: {exc}") from exc


def effective_config(path: Path | None = None) -> Config:
    """Settings as spotipulse would use them, even before you've logged in (credentials may be empty)."""
    path = path or config_path()
    config = load_config(path) if path.is_file() else None
    if config is not None:
        return config
    # No credentials yet: validate the [app] section on a placeholder config.
    config = Config("", "")
    for key, raw in read_settings(path).items():
        if key in SETTINGS_BY_KEY:
            config = with_setting(config, key, parse_setting(key, raw))
    return config
