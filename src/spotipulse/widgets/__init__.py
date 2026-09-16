"""Tab views of the dashboard, plus the few helpers they share."""

from __future__ import annotations

from functools import lru_cache

from PIL import Image, ImageDraw
from textual.containers import Vertical

# Imported before Textual starts: textual-image probes the terminal's cell size at import time.
from textual_image.widget import Image as CoverArt  # noqa: F401


@lru_cache(maxsize=1)
def placeholder_cover() -> Image.Image:
    """A dark square with a green note, shown when there is no cover to display."""
    size = 300
    image = Image.new("RGB", (size, size), (40, 40, 40))
    draw = ImageDraw.Draw(image)
    green = (29, 185, 84)
    draw.ellipse((95, 185, 155, 235), fill=green)
    draw.rectangle((143, 70, 155, 210), fill=green)
    draw.polygon([(155, 70), (215, 95), (215, 125), (155, 100)], fill=green)
    return image


class LazyView(Vertical):
    """A tab view that loads its data the first time it's shown, and again once marked stale."""

    stale: bool = True

    def activate(self) -> None:
        if self.stale:
            self.stale = False
            self.load()

    def load(self) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    def is_visible_tab(self) -> bool:
        pane = self.parent
        tabs = self.app.query_one("#tabs")
        return pane is not None and getattr(tabs, "active", None) == pane.id
