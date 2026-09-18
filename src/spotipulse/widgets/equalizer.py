"""Decorative equalizer bars next to "Now playing".

Purely cosmetic: Spotify removed its audio-analysis data in 2024, so the bars can't follow the music.
They bounce while something plays and settle down when it's paused.
"""

from __future__ import annotations

import random

from rich.text import Text
from textual.widgets import Static

from .. import palette

LEVELS = " ▁▂▃▄▅▆▇█"
TOP = len(LEVELS) - 1


def next_levels(levels: list[int], rng: random.Random) -> list[int]:
    """One animation step: each bar drifts towards a random height, sometimes jumping."""
    result = []
    for level in levels:
        if rng.random() < 0.18:
            level = rng.randint(2, TOP)
        else:
            level += rng.choice((-2, -1, -1, 1, 1, 2))
        result.append(max(1, min(TOP, level)))
    return result


def render_bars(levels: list[int], color: str | None) -> Text:
    return Text("".join(LEVELS[level] for level in levels), style=color or "dim")


class Equalizer(Static):
    DEFAULT_CSS = """
    Equalizer {
        width: auto;
        height: 1;
        margin-right: 2;
    }
    """

    def __init__(self, bars: int = 6, fps: float = 8, **kwargs) -> None:
        super().__init__("", **kwargs)
        self._rng = random.Random()
        self._levels = [2] * bars
        self._fps = fps
        self._playing = False
        self.color: str | None = None  # None -> the theme's green

    def on_mount(self) -> None:
        self._timer = self.set_interval(1 / self._fps, self._step, pause=True)
        self._draw()

    def set_playing(self, playing: bool) -> None:
        if playing == self._playing:
            return
        self._playing = playing
        if playing:
            self._timer.resume()
        else:
            self._timer.pause()
            self._levels = [1] * len(self._levels)  # settle flat while paused
        self._draw()

    def set_color(self, color: str | None) -> None:
        self.color = color
        self._draw()

    def _step(self) -> None:
        self._levels = next_levels(self._levels, self._rng)
        self._draw()

    def _draw(self) -> None:
        color = (self.color or palette.bright()) if self._playing else None
        self.update(render_bars(self._levels, color))
