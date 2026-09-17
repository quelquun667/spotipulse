"""The `?` overlay listing every keyboard shortcut."""

from __future__ import annotations

from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

SECTIONS: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "Tabs",
        [
            ("1 / &", "Now Playing"),
            ("2 / é", "Top"),
            ('3 / "', "Genres"),
            ("4 / '", "History"),
            ("5 / (", "Recently Played"),
            ("6 / -", "Profile"),
        ],
    ),
    (
        "Top & Genres",
        [
            ("w  m  y", "4 Weeks / 6 Months / 1 Year"),
            ("← →", "previous / next period (on the period tabs)"),
            ("/", "filter tracks & artists"),
            ("Esc", "clear the filter"),
            ("↑ ↓", "move in a table (updates the cover)"),
        ],
    ),
    (
        "General",
        [
            ("c", "compact view (just what's playing)"),
            ("r", "refresh everything"),
            ("e", "export a PNG recap of the selected period"),
            ("Tab", "move focus between widgets"),
            ("? / ,", "show / hide this help"),
            ("Ctrl+L", "redraw the screen (if your terminal leaves artifacts)"),
            ("L", "log out and quit"),
            ("q", "quit"),
        ],
    ),
]


def help_table() -> Table:
    table = Table.grid(padding=(0, 3))
    table.add_column(justify="right", style="bold #1ED760", no_wrap=True)
    table.add_column()
    for index, (section, keys) in enumerate(SECTIONS):
        if index:
            table.add_row("", "")
        table.add_row("", Text(section.upper(), style="bold dim"))
        for key, description in keys:
            table.add_row(key, description)
    return table


class HelpScreen(ModalScreen):
    BINDINGS = [
        Binding("question_mark,escape,q,f1", "dismiss", "Close"),
    ]

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="help"):
            yield Static(help_table(), id="help-keys")
            yield Static("[dim]Press ? or Esc to close[/dim]", id="help-hint")

    def on_mount(self) -> None:
        self.query_one("#help").border_title = "Keyboard shortcuts"

    def on_click(self) -> None:
        self.dismiss()
