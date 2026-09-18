import pytest

from spotipulse.config import (
    DEFAULT_REDIRECT_URI,
    ConfigError,
    config_path,
    load_config,
    save_config,
    token_cache_path,
)


def test_paths_follow_spotipulse_home(isolated_home):
    assert config_path() == isolated_home / "config.toml"
    assert token_cache_path() == isolated_home / "token_cache"


def test_missing_config_returns_none():
    assert load_config() is None


def test_save_then_load_roundtrip():
    save_config("my-id", 'se"cr\\et')
    config = load_config()
    assert config is not None
    assert config.client_id == "my-id"
    assert config.client_secret == 'se"cr\\et'
    assert config.redirect_uri == DEFAULT_REDIRECT_URI
    assert config.refresh_interval == 3


def test_blank_credentials_count_as_missing(isolated_home):
    isolated_home.mkdir(parents=True)
    config_path().write_text('[spotify]\nclient_id = ""\nclient_secret = "x"\n', encoding="utf-8")
    assert load_config() is None


def test_invalid_toml_raises(isolated_home):
    isolated_home.mkdir(parents=True)
    config_path().write_text("[spotify\nclient_id = ", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config()


def test_refresh_interval_has_a_floor(isolated_home):
    isolated_home.mkdir(parents=True)
    config_path().write_text(
        '[spotify]\nclient_id = "a"\nclient_secret = "b"\n'
        '[app]\nrefresh_interval = 0.1\nexport_dir = "~/out"\n',
        encoding="utf-8",
    )
    config = load_config()
    assert config.refresh_interval == 1.0
    assert config.resolved_export_dir().name == "out"


def test_covers_defaults_to_blocks_and_rejects_nonsense(isolated_home):
    save_config("id", "secret")
    assert load_config().covers == "auto"
    isolated_home.joinpath("other.toml").write_text(
        '[spotify]\nclient_id = "a"\nclient_secret = "b"\n[app]\ncovers = "AUTO"\n', encoding="utf-8"
    )
    assert load_config(isolated_home / "other.toml").covers == "auto"
    isolated_home.joinpath("bad.toml").write_text(
        '[spotify]\nclient_id = "a"\nclient_secret = "b"\n[app]\ncovers = "sixel"\n', encoding="utf-8"
    )
    with pytest.raises(ConfigError):
        load_config(isolated_home / "bad.toml")


def test_new_settings_defaults_and_values(isolated_home):
    save_config("id", "secret")
    config = load_config()
    assert (config.recap_format, config.animations, config.accent_from_cover, config.theme) == (
        "feed",
        True,
        False,
        "dark",
    )
    isolated_home.joinpath("custom.toml").write_text(
        '[spotify]\nclient_id = "a"\nclient_secret = "b"\n'
        '[app]\nrecap_format = "Story"\nanimations = false\naccent_from_cover = true\ntheme = "light"\n',
        encoding="utf-8",
    )
    config = load_config(isolated_home / "custom.toml")
    assert (config.recap_format, config.animations, config.accent_from_cover, config.theme) == (
        "story",
        False,
        True,
        "light",
    )


def test_quoted_booleans_are_rejected_with_a_clear_message(isolated_home):
    isolated_home.mkdir(parents=True, exist_ok=True)
    isolated_home.joinpath("bad.toml").write_text(
        '[spotify]\nclient_id = "a"\nclient_secret = "b"\n[app]\nanimations = "false"\n', encoding="utf-8"
    )
    with pytest.raises(ConfigError, match="without quotes"):
        load_config(isolated_home / "bad.toml")
