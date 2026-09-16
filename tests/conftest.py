import pytest

from spotipulse.api import Artist, Track


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Never touch the real ~/.config/spotipulse during tests."""
    monkeypatch.setenv("SPOTIPULSE_HOME", str(tmp_path / "spotipulse"))
    return tmp_path / "spotipulse"


def make_track(i: int = 0, duration_ms: int = 200_000) -> Track:
    return Track(f"track{i}", f"Track {i}", (f"Artist {i}",), f"Album {i}", duration_ms)


def make_artist(i: int, genres: tuple[str, ...] | None) -> Artist:
    return Artist(f"artist{i}", f"Artist {i}", genres)
