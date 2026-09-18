from datetime import datetime

from PIL import Image

from spotipulse.export import HEIGHT, WIDTH, render_recap
from spotipulse.genres import top_genres
from spotipulse.palette import accent_color

from conftest import make_artist, make_track


def test_render_recap_writes_png(tmp_path):
    tracks = [make_track(i) for i in range(10)]
    artists = [make_artist(i, ("indie pop", "house")) for i in range(10)]
    requested = []

    def images(url):
        requested.append(url)
        return Image.new("RGB", (64, 64), (200, 40, 40))

    tracks = [t.__class__(**{**t.__dict__, "image_url": f"cover{i}"}) for i, t in enumerate(tracks)]
    path = render_recap(
        tracks,
        artists,
        top_genres(artists),
        "4 Weeks",
        "≈ 12h 30m listened",
        tmp_path / "out",
        now=datetime(2026, 9, 16, 21, 30),
        images=images,
        user_name="Noah",
    )
    assert path.name == "spotipulse-recap-20260916-213000.png"
    with Image.open(path) as image:
        assert image.size == (WIDTH, HEIGHT)
    # the #1 cover plus tracks #2-#6
    assert requested[:6] == [f"cover{i}" for i in range(6)]


def test_render_recap_handles_empty_data(tmp_path):
    path = render_recap([], [], [], "1 Year", None, tmp_path)
    assert path.exists()


def test_render_recap_survives_broken_image_loader(tmp_path):
    def images(url):
        raise OSError("offline")

    track = make_track(0)
    track = track.__class__(**{**track.__dict__, "name": "A " * 80, "image_url": "x"})
    path = render_recap([track], [], [], "6 Months", None, tmp_path, images=images)
    assert path.exists()


def test_accent_color():
    assert accent_color(None) == (30, 215, 96)
    assert accent_color(Image.new("RGB", (10, 10), (128, 128, 128))) == (30, 215, 96)  # grey -> fallback
    r, g, b = accent_color(Image.new("RGB", (10, 10), (200, 30, 30)))
    assert r > g and r > b


def test_every_format_has_its_size(tmp_path):
    from spotipulse.export import LAYOUTS

    tracks = [make_track(i) for i in range(8)]
    artists = [make_artist(i, ("pop",)) for i in range(8)]
    for i, fmt in enumerate(("feed", "story", "square")):
        path = render_recap(
            tracks,
            artists,
            top_genres(artists),
            "4 Weeks",
            "≈ 1h listened",
            tmp_path,
            now=datetime(2026, 9, 18, 12, i),
            fmt=fmt,
            user_name="Noah",
            avatar_url="me",
            images=lambda url: Image.new("RGB", (40, 40), (30, 90, 200)),
        )
        layout = LAYOUTS[fmt]
        with Image.open(path) as image:
            assert image.size == (layout.width, layout.height)
        assert path.name.endswith(".png") and (fmt == "feed") == ("-" + fmt not in path.name)


def test_unknown_format_falls_back_to_feed(tmp_path):
    path = render_recap([], [], [], "4 Weeks", None, tmp_path, fmt="poster")
    with Image.open(path) as image:
        assert image.size == (WIDTH, HEIGHT)
