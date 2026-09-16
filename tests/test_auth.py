from unittest.mock import MagicMock

import requests
from spotipy.oauth2 import SpotifyOauthError

from spotipulse.auth import TokenStatus, check_token, logout
from spotipulse.config import token_cache_path


def _oauth(cached, validate=None, side_effect=None):
    oauth = MagicMock()
    oauth.cache_handler.get_cached_token.return_value = cached
    oauth.validate_token.return_value = validate
    oauth.validate_token.side_effect = side_effect
    return oauth


def _write_cache():
    path = token_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")
    return path


def test_missing_token():
    assert check_token(_oauth(None)) is TokenStatus.MISSING


def test_valid_token():
    token = {"access_token": "x"}
    assert check_token(_oauth(token, validate=token)) is TokenStatus.VALID


def test_dead_refresh_token_is_expired_and_cleared():
    path = _write_cache()
    oauth = _oauth({"refresh_token": "old"}, side_effect=SpotifyOauthError("invalid_grant"))
    assert check_token(oauth) is TokenStatus.EXPIRED
    assert not path.exists()


def test_offline_keeps_token():
    path = _write_cache()
    oauth = _oauth({"refresh_token": "r"}, side_effect=requests.ConnectionError())
    assert check_token(oauth) is TokenStatus.VALID
    assert path.exists()


def test_scope_mismatch_forces_new_login():
    path = _write_cache()
    assert check_token(_oauth({"scope": "user-top-read"}, validate=None)) is TokenStatus.NEEDS_CONSENT
    assert not path.exists()


def test_logout_reports_whether_there_was_a_token():
    assert logout() is False
    _write_cache()
    assert logout() is True
