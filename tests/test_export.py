from datetime import datetime

from PIL import Image

from spotipulse.export import HEIGHT, WIDTH, render_recap
from spotipulse.genres import top_genres

from conftest import make_artist, make_track


def test_render_recap_writes_png(tmp_path):
    tracks = [make_track(i) for i in range(10)]
    artists = [make_artist(i, ("indie pop", "house")) for i in range(10)]
    path = render_recap(
        tracks,
        artists,
        top_genres(artists),
        "4 Weeks",
        "≈ 12h 30m listened",
        tmp_path / "out",
        now=datetime(2026, 9, 16, 21, 30),
    )
    assert path.name == "spotipulse-recap-20260916-213000.png"
    with Image.open(path) as image:
        assert image.size == (WIDTH, HEIGHT)


def test_render_recap_handles_empty_data(tmp_path):
    path = render_recap([], [], [], "1 Year", None, tmp_path)
    assert path.exists()
