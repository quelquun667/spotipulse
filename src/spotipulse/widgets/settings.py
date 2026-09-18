"""The `s` screen: browse and change settings; every change is saved to config.toml right away."""

from __future__ import annotations

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Input, Static

from .. import palette
from ..config import SETTINGS, ConfigError, Setting, display_value, get_setting, set_setting, write_value


def _next_value(setting: Setting, current: object, step: int) -> object:
    """The value ← / → moves to. Paths are typed instead (returns None)."""
    if setting.kind == "choice":
        choices = setting.choices
        index = choices.index(current) if current in choices else 0
        return choices[(index + step) % len(choices)]
    if setting.kind == "bool":
        return not current
    if setting.kind == "number":
        return max(1, int(float(current)) + step)
    return None


class PathInputScreen(ModalScreen[str | None]):
    """Type a folder for `export_dir` (empty = back to the default)."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, current: str) -> None:
        super().__init__()
        self._current = current

    def compose(self) -> ComposeResult:
        with Vertical(id="path-input"):
            yield Static("Folder where recap cards are saved. Leave empty for the default (Pictures).")
            yield Input(value=self._current, placeholder="~/Pictures", id="path-value")
            yield Static("[dim]Enter to save  ·  Esc to cancel[/dim]")

    def on_mount(self) -> None:
        self.query_one("#path-input").border_title = "export_dir"
        self.query_one(Input).focus()

    @on(Input.Submitted)
    def _submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def action_cancel(self) -> None:
        self.dismiss(None)


class SettingsScreen(ModalScreen):
    BINDINGS = [
        Binding("escape,s,q", "close", "Close"),
        # priority: the table would otherwise use ← → to scroll sideways and Enter to "select"
        Binding("left", "change(-1)", "Previous value", show=False, priority=True),
        Binding("right,enter,space", "change(1)", "Next value", show=False, priority=True),
        Binding("backspace,delete,d", "reset", "Reset to default", show=False),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="settings"):
            yield DataTable(id="settings-table", cursor_type="row", show_header=False)
            yield Static("", id="settings-help")
            yield Static(
                "[dim]↑ ↓ choose  ·  ← → Enter change  ·  d reset  ·  Esc close[/dim]\n"
                "[dim]Saved to config.toml as you go.[/dim]",
                id="settings-hint",
            )

    def on_mount(self) -> None:
        panel = self.query_one("#settings")
        panel.border_title = "Settings"
        self.app.fade_in(panel)
        table = self.query_one(DataTable)
        table.add_column("Setting", key="setting", width=20)
        table.add_column("Value", key="value", width=34)
        for setting in SETTINGS:
            table.add_row(setting.key, self._value_cell(setting.key), key=setting.key)
        table.focus()
        self._show_help(SETTINGS[0])

    def _value_cell(self, key: str) -> Text:
        style = f"bold {palette.bright()}"
        if get_setting(key).kind == "path":
            folder = self.app.config.export_dir
            shown = f"{folder}" if folder else "default (Pictures)"
            if len(shown) > 28:
                shown = "…" + shown[-27:]
            return Text(f"✎ {shown}", style=style)
        return Text(f"‹ {display_value(self.app.config, key)} ›", style=style)

    def _highlighted(self) -> Setting:
        table = self.query_one(DataTable)
        return SETTINGS[table.cursor_row]

    @on(DataTable.RowHighlighted)
    def _row_changed(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key and event.row_key.value:
            self._show_help(get_setting(event.row_key.value))

    def _show_help(self, setting: Setting) -> None:
        text = Text()
        text.append(setting.description, style="bold")
        if setting.choices:
            text.append(f"\n{' · '.join(setting.choices)}", style="dim")
        default = "Pictures" if setting.default is None else display_default(setting)
        text.append(f"\nDefault: {default}", style="dim")
        if not setting.live:
            text.append("\nApplies the next time you start spotipulse.", style=palette.red())
        self.query_one("#settings-help", Static).update(text)

    # ---------- changing values ----------

    def action_change(self, step: int) -> None:
        setting = self._highlighted()
        current = getattr(self.app.config, setting.key)
        if setting.kind == "path":
            self.app.push_screen(
                PathInputScreen(str(current) if current else ""),
                lambda typed: self._save(setting, typed) if typed is not None else None,
            )
            return
        self._save(setting, _next_value(setting, current, step))

    def action_reset(self) -> None:
        setting = self._highlighted()
        write_value("app", setting.key, None)
        self._applied(setting, None)

    def _save(self, setting: Setting, raw: object) -> None:
        try:
            value = set_setting(setting.key, raw)
        except (ConfigError, OSError) as exc:
            self.app.notify(str(exc), severity="error")
            return
        self._applied(setting, value)

    def _applied(self, setting: Setting, file_value: object) -> None:
        live = self.app.apply_setting(setting.key, file_value)
        self.query_one(DataTable).update_cell(setting.key, "value", self._value_cell(setting.key))
        shown = display_value(self.app.config, setting.key)
        message = f"{setting.key} = {shown}" + ("" if live else " — restart spotipulse to apply")
        self.app.notify(message, timeout=2.5 if live else 5)

    def action_close(self) -> None:
        self.dismiss()


def display_default(setting: Setting) -> str:
    if isinstance(setting.default, bool):
        return "true" if setting.default else "false"
    return str(setting.default)
