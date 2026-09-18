"""Colors used in Rich text (tables, charts, labels), following the current theme.

CSS already follows the Textual theme through $primary & co.; this covers the text built in Python.
"""

from __future__ import annotations

import colorsys

from PIL import Image

DARK = {"green": "#1DB954", "bright": "#1ED760", "red": "#E5534B"}
# Darker greens and red: Spotify's bright green is unreadable on a white background.
LIGHT = {"green": "#138A43", "bright": "#0F7A3A", "red": "#C62828"}

_current = dict(DARK)


def set_dark(dark: bool) -> None:
    _current.update(DARK if dark else LIGHT)


def green() -> str:
    return _current["green"]


def bright() -> str:
    """The emphasis green: highlights, active values, "up" trends."""
    return _current["bright"]


def red() -> str:
    return _current["red"]


SPOTIFY_GREEN = (30, 215, 96)


def accent_color(image: Image.Image | None, value: float = 0.85) -> tuple[int, int, int]:
    """A vivid version of the cover's dominant color, or Spotify green without a usable cover.

    `value` is the brightness of the result: ~0.85 reads well on dark backgrounds, ~0.5 on light ones.
    """
    if image is None:
        return SPOTIFY_GREEN
    small = image.convert("RGB").resize((24, 24), Image.BILINEAR)
    best, best_score = None, -1.0
    raw = small.tobytes()
    for r, g, b in zip(raw[0::3], raw[1::3], raw[2::3], strict=True):
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        score = s * v
        if score > best_score:
            best, best_score = (h, s, v), score
    if best is None or best_score < 0.12:
        return SPOTIFY_GREEN
    h, s, _ = best
    r, g, b = colorsys.hsv_to_rgb(h, max(0.55, min(s, 0.85)), value)
    return int(r * 255), int(g * 255), int(b * 255)


def to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)
