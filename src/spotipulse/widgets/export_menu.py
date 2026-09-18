"""Shift+E: pick the recap card format before exporting."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

FORMAT_CHOICES: list[tuple[str, str, str]] = [
    ("feed", "Feed  1080×1350", "Instagram / Discord post (4:5)"),
    ("story", "Story  1080×1920", "Instagram / Snapchat story, phone wallpaper (9:16)"),
    ("square", "Square  1080×1080", "square post, thumbnail (1:1)"),
]


def _option(key: str, title: str, description: str, default: str) -> Option:
    label = Text()
    label.append(title, style="bold")
    if key == default:
        label.append("  (default)", style="dim")
    label.append(f"\n{description}", style="dim")
    return Option(label, id=key)


class ExportScreen(ModalScreen[str | None]):
    """Returns the chosen format, or None if cancelled."""

    BINDINGS = [
        Binding("escape,q", "cancel", "Cancel"),
        # 1/2/3, or the unshifted AZERTY keys (& é ") for the same spots
        Binding("1,ampersand", "choose('feed')", show=False),
        Binding("2,é", "choose('story')", show=False),
        Binding("3,quotation_mark", "choose('square')", show=False),
    ]

    def __init__(self, default: str = "feed") -> None:
        super().__init__()
        self._default = default

    def compose(self) -> ComposeResult:
        with Vertical(id="export-menu"):
            yield OptionList(
                *(_option(k, t, d, self._default) for k, t, d in FORMAT_CHOICES), id="export-options"
            )
            yield Static("[dim]↑ ↓ Enter  ·  1 2 3  ·  Esc to cancel[/dim]", id="export-hint")

    def on_mount(self) -> None:
        menu = self.query_one("#export-menu")
        menu.border_title = "Export recap as…"
        self.app.fade_in(menu)
        options = self.query_one(OptionList)
        options.highlighted = [k for k, _, _ in FORMAT_CHOICES].index(self._default)
        options.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option.id)

    def action_choose(self, fmt: str) -> None:
        self.dismiss(fmt)

    def action_cancel(self) -> None:
        self.dismiss(None)
