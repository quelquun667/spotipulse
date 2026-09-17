"""Tab views of the dashboard, plus the few helpers they share."""

from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache

from PIL import Image, ImageDraw
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import DataTable, Static

# Imported before Textual starts: textual-image probes the terminal's cell size at import time.
from textual_image.widget import HalfcellImage, UnicodeImage
from textual_image.widget import Image as AutoImage

# How album art is drawn. "auto" (the default) uses the terminal's image protocol (Sixel / Kitty) for real
# images; "blocks" draws them with colored half-block characters, which every terminal redraws cleanly.
COVER_MODES = ("blocks", "auto", "unicode", "off")
_COVER_WIDGETS = {"blocks": HalfcellImage, "auto": AutoImage, "unicode": UnicodeImage}
_cover_mode = "auto"


def set_cover_mode(mode: str) -> None:
    global _cover_mode
    _cover_mode = mode if mode in COVER_MODES else "auto"


class NoCover(Static):
    """Stand-in used when covers are turned off: keeps the layout, draws nothing."""

    @property
    def image(self):
        return None

    @image.setter
    def image(self, value) -> None:
        pass


def cover_art(image=None, **kwargs) -> Widget:
    """An album-art widget honouring the `covers` setting. Set `.image` to a PIL image to update it."""
    if _cover_mode == "off":
        return NoCover(**kwargs)
    return _COVER_WIDGETS[_cover_mode](image, **kwargs)


# (key, label, minimum width, share of the leftover space). A share of 0 keeps the column at its minimum.
ColumnSpec = tuple[str, str, int, int]


def column_widths(available: int, spec: Sequence[ColumnSpec]) -> list[tuple[str, str, int]]:
    """Share the table's width between columns: fixed ones keep their size, the rest split what's left."""
    padding = 2 * len(spec) + 1  # one cell each side of every column, plus the scrollbar
    leftover = max(0, available - padding - sum(minimum for _, _, minimum, _ in spec))
    shares = sum(share for *_, share in spec) or 1
    return [(key, label, minimum + leftover * share // shares) for key, label, minimum, share in spec]


def fit_columns(table: DataTable, spec: Sequence[ColumnSpec]) -> bool:
    """Rebuild the table's columns for its current width. Returns True if they changed (rows are cleared)."""
    available = table.size.width
    if available <= 0:
        return False
    layout = column_widths(available, spec)
    if getattr(table, "_spotipulse_layout", None) == layout:
        return False
    table.clear(columns=True)
    for key, label, width in layout:
        table.add_column(label, key=key, width=width)
    table._spotipulse_layout = layout
    return True


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
