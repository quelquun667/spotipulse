"""Settings registry, file editing, `spotipulse config` and the in-app Settings screen."""

import asyncio

import pytest

from spotipulse.app import SpotipulseApp
from spotipulse.cli import main
from spotipulse.config import (
    SETTINGS,
    Config,
    ConfigError,
    _write_file,
    config_path,
    effective_config,
    load_config,
    parse_setting,
    read_settings,
    save_config,
    set_setting,
    template,
    write_value,
)
from spotipulse.db import HistoryDB

# ---------- parsing ----------


@pytest.mark.parametrize(
    ("key", "raw", "expected"),
    [
        ("theme", "Light", "light"),
        ("covers", '"blocks"', "blocks"),
        ("animations", "off", False),
        ("accent_from_cover", "yes", True),
        ("refresh_interval", "5", 5),
        ("refresh_interval", "2.5", 2.5),
        ("export_dir", "~/Desktop", "~/Desktop"),
        ("export_dir", "", None),
    ],
)
def test_parse_setting(key, raw, expected):
    assert parse_setting(key, raw) == expected


@pytest.mark.parametrize(
    ("key", "raw", "message"),
    [
        ("theme", "blue", "one of dark, light"),
        ("animations", "maybe", "true or false"),
        ("refresh_interval", "0", "1 or more"),
        ("refresh_interval", "fast", "a number"),
        ("colour", "red", "unknown setting"),
    ],
)
def test_parse_setting_rejects_bad_values(key, raw, message):
    with pytest.raises(ConfigError, match=message):
        parse_setting(key, raw)


def test_every_setting_has_a_config_field():
    fields = Config("a", "b").__dataclass_fields__
    assert all(setting.key in fields for setting in SETTINGS)


# ---------- editing the file ----------


def test_template_lists_every_setting_commented_out(tmp_path):
    path = tmp_path / "config.toml"
    _write_file(path, template("id", "secret"))
    assert read_settings(path) == {}  # all commented: defaults apply
    text = path.read_text(encoding="utf-8")
    for setting in SETTINGS:
        assert f"# {setting.key} = " in text
    assert load_config(path).client_id == "id"


def test_set_uncomments_in_place_and_reset_comments_back(tmp_path):
    path = tmp_path / "config.toml"
    _write_file(path, template("id", "secret"))
    before = path.read_text(encoding="utf-8").splitlines()
    set_setting("theme", "light", path)
    after = path.read_text(encoding="utf-8").splitlines()
    assert len(after) == len(before)  # the commented line became the setting, nothing added
    assert 'theme = "light"' in after
    write_value("app", "theme", None, path)
    assert read_settings(path) == {}
    assert '# theme = "dark"' in path.read_text(encoding="utf-8")


def test_set_keeps_other_lines_and_comments(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        '# my notes\n[spotify]\nclient_id = "a"\nclient_secret = "b"\n\n'
        '[app]\n# keep me\ncovers = "blocks"\n',
        encoding="utf-8",
    )
    set_setting("animations", "false", path)
    set_setting("covers", "off", path)
    text = path.read_text(encoding="utf-8")
    assert "# my notes" in text and "# keep me" in text
    assert read_settings(path) == {"covers": "off", "animations": False}


def test_set_creates_the_app_section_when_missing(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[spotify]\nclient_id = "a"\nclient_secret = "b"\n', encoding="utf-8")
    set_setting("recap_format", "story", path)
    assert load_config(path).recap_format == "story"


def test_save_config_keeps_existing_settings(isolated_home):
    _write_file(config_path(), template())
    set_setting("theme", "light")
    config = save_config("new-id", "new-secret")
    assert (config.client_id, config.client_secret, config.theme) == ("new-id", "new-secret", "light")


def test_effective_config_works_before_login(isolated_home):
    _write_file(config_path(), template())  # empty credentials
    set_setting("recap_format", "square")
    assert effective_config().recap_format == "square"


# ---------- spotipulse config ... ----------


def test_cli_set_get_list_reset(isolated_home, capsys):
    assert main(["config", "set", "theme", "light"]) == 0
    assert "theme = light" in capsys.readouterr().out
    assert main(["config", "get", "theme"]) == 0
    assert capsys.readouterr().out.strip() == "light"
    assert main(["config"]) == 0
    listing = capsys.readouterr().out
    assert "theme" in listing and "light  *" in listing and "refresh_interval" in listing
    assert main(["config", "reset", "theme"]) == 0
    assert "theme = dark" in capsys.readouterr().out


def test_cli_rejects_bad_values_without_touching_the_file(isolated_home, capsys):
    assert main(["config", "set", "animations", "maybe"]) == 1
    assert "true or false" in capsys.readouterr().err
    assert main(["config", "set", "colour", "red"]) == 1
    assert "unknown setting" in capsys.readouterr().err
    assert read_settings() == {}


def test_cli_config_path_and_edit(isolated_home, capsys, monkeypatch):
    opened = []
    monkeypatch.setattr("spotipulse.config_cli.open_in_editor", opened.append)
    assert main(["config", "path"]) == 0
    assert capsys.readouterr().out.strip() == str(config_path())
    assert main(["--config"]) == 0
    assert opened == [config_path()]
    assert config_path().is_file()  # created from the template


# ---------- the Settings screen ----------


def _app(**overrides):
    from spotipulse.app import SpotipulseApp
    from test_app import FakeAPI

    return SpotipulseApp(FakeAPI(), HistoryDB(":memory:"), Config("id", "secret", **overrides), splash=False)


def test_settings_screen_changes_and_saves_the_theme(isolated_home):
    app = _app()
    seen = {}

    async def drive():
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.pause(0.3)
            await pilot.press("s")
            await pilot.pause(0.3)
            seen["screen"] = type(app.screen).__name__
            await pilot.press("right")  # theme is the first row: dark -> light
            await pilot.pause(0.3)
            seen["theme"] = app.theme
            await pilot.press("escape")
            await pilot.pause(0.2)
            seen["after"] = type(app.screen).__name__

    asyncio.run(drive())
    assert seen == {"screen": "SettingsScreen", "theme": "spotipulse-light", "after": "Screen"}
    assert read_settings() == {"theme": "light"}


def test_settings_screen_turns_animations_off_live_and_resets(isolated_home):
    from spotipulse.widgets.equalizer import Equalizer

    app = _app()
    counts = []

    async def drive():
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.pause(0.5)
            counts.append(len(app.query(Equalizer)))
            await pilot.press("s")
            await pilot.pause(0.2)
            for _ in range(3):  # theme, covers, accent_from_cover -> animations
                await pilot.press("down")
            await pilot.press("enter")
            await pilot.pause(0.3)
            counts.append(len(app.query(Equalizer)))
            assert read_settings() == {"animations": False}
            await pilot.press("d")  # back to the default: equalizer returns
            await pilot.pause(0.3)
            counts.append(len(app.query(Equalizer)))

    asyncio.run(drive())
    assert counts == [1, 0, 1]
    assert read_settings() == {}


def test_settings_screen_types_the_export_folder(isolated_home, tmp_path):
    app = _app()
    target = tmp_path / "cards"

    async def drive():
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.pause(0.3)
            await pilot.press("s")
            await pilot.pause(0.2)
            for _ in range(5):  # down to export_dir
                await pilot.press("down")
            await pilot.press("enter")
            await pilot.pause(0.3)
            assert type(app.screen).__name__ == "PathInputScreen"
            app.screen.query_one("Input").value = str(target)
            await pilot.press("enter")
            await pilot.pause(0.3)

    asyncio.run(drive())
    assert read_settings() == {"export_dir": str(target)}
    assert app.config.export_dir == target


def test_turning_accent_from_cover_off_clears_the_tint(isolated_home):
    """The panel used to keep the colour of whatever was playing when the setting went off."""
    from PIL import Image

    from spotipulse.widgets.now_playing import NowPlayingView

    class ColourfulAPI(_fake_api_class()):
        def image(self, url):
            return Image.new("RGB", (32, 32), (200, 30, 30))

    app = SpotipulseApp(
        ColourfulAPI(), HistoryDB(":memory:"), Config("id", "secret", accent_from_cover=True), splash=False
    )
    seen = {}

    async def drive():
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.pause(1.0)
            view = app.query_one(NowPlayingView)
            body = app.query_one("#np-body")
            seen["on"] = (view.accent, body.styles.border_top[1].hex.upper())
            app.apply_setting("accent_from_cover", False)
            await pilot.pause(1.0)
            seen["off"] = (view.accent, body.styles.border_top[1].hex.upper())

    asyncio.run(drive())
    tint = seen["on"][0]
    assert tint is not None and seen["on"][1] == tint.upper()  # the panel took the cover colour
    assert seen["off"][0] is None and seen["off"][1] != tint.upper()  # and gave it back


def _fake_api_class():
    from test_app import FakeAPI

    tracks = FakeAPI().tracks

    class WithCovers(FakeAPI):
        def __init__(self):
            super().__init__()
            self.tracks = [t.__class__(**{**t.__dict__, "image_url": "cover"}) for t in tracks]

    return WithCovers
