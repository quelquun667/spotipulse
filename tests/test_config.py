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
