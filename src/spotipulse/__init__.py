"""spotipulse — a terminal dashboard for your Spotify stats."""

from importlib import resources
from pathlib import Path

# Single source of truth for the version (pyproject.toml reads it from here).
__version__ = "0.2.0"


def asset_path(name: str) -> Path | None:
    """Locate a bundled asset (wheel install) or fall back to the repo's assets/ folder."""
    bundled = resources.files("spotipulse") / "assets" / name
    if bundled.is_file():
        return Path(str(bundled))
    repo = Path(__file__).resolve().parents[2] / "assets" / name
    return repo if repo.is_file() else None
