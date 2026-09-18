"""`spotipulse config …` and `spotipulse --config`: read and change settings from the command line."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from .config import (
    SETTINGS,
    ConfigError,
    _write_file,
    config_path,
    display_value,
    effective_config,
    get_setting,
    read_settings,
    set_setting,
    template,
    toml_literal,
    write_value,
)


def ensure_config_file() -> Path:
    """The config file, created from the template (every setting commented out) if it doesn't exist."""
    path = config_path()
    if not path.is_file():
        _write_file(path, template())
    return path


def open_in_editor(path: Path) -> None:
    """Open the file in $VISUAL / $EDITOR if set, else the system's default app (Notepad as a last resort)."""
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if editor:
        subprocess.call([*shlex.split(editor, posix=os.name != "nt"), str(path)])
        return
    if sys.platform == "win32":
        try:
            os.startfile(path)  # type: ignore[attr-defined]  # whatever app opens .toml files
        except OSError:
            subprocess.Popen(["notepad.exe", str(path)])
        return
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    if shutil.which(opener):
        subprocess.Popen([opener, str(path)])
        return
    fallback = next((e for e in ("nano", "vim", "vi") if shutil.which(e)), None)
    if fallback is None:
        raise ConfigError(f"no editor found: set $EDITOR, or open {path} yourself")
    subprocess.call([fallback, str(path)])


def _allowed(setting) -> str:
    if setting.choices:
        return " | ".join(setting.choices)
    return {"bool": "true | false", "number": "number ≥ 1", "path": "folder path"}[setting.kind]


def _default(setting) -> str:
    return "~/Pictures" if setting.default is None else toml_literal(setting.default).strip('"')


def list_settings() -> str:
    config = effective_config()
    written = read_settings()
    rows = [("SETTING", "VALUE", "DEFAULT", "ALLOWED")]
    for setting in SETTINGS:
        value = display_value(config, setting.key)
        if setting.key in written:
            value += "  *"
        rows.append((setting.key, value, _default(setting), _allowed(setting)))
    widths = [max(len(row[i]) for row in rows) for i in range(4)]
    lines = ["  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)).rstrip() for row in rows]
    lines.append("")
    lines.append(f"* set in {config_path()}")
    return "\n".join(lines)


def run(action: str | None, key: str | None, value: str | None) -> int:
    """Returns the process exit code."""
    try:
        if action in (None, "list"):
            print(list_settings())
        elif action == "path":
            print(config_path())
        elif action == "edit":
            path = ensure_config_file()
            print(f"Opening {path}")
            open_in_editor(path)
        elif action == "get":
            if not key:
                raise ConfigError("usage: spotipulse config get <setting>")
            get_setting(key)
            print(display_value(effective_config(), key))
        elif action == "set":
            if not key or value is None:
                raise ConfigError("usage: spotipulse config set <setting> <value>")
            get_setting(key)
            before = display_value(effective_config(), key)
            ensure_config_file()
            set_setting(key, value)
            after = display_value(effective_config(), key)
            print(f"{key} = {after}" + (f"   (was {before})" if before != after else "   (unchanged)"))
            print("Restart spotipulse to apply it, or change settings live with the s key in the app.")
        elif action == "reset":
            if not key:
                raise ConfigError("usage: spotipulse config reset <setting>")
            get_setting(key)
            if config_path().is_file():
                write_value("app", key, None)
            print(f"{key} = {display_value(effective_config(), key)}   (default)")
        else:
            raise ConfigError(f"unknown config action {action!r}")
    except ConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0
