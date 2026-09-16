"""OAuth flow (SpotifyOAuth) and token cache handling."""

from __future__ import annotations

from enum import Enum

import requests
from spotipy.cache_handler import CacheFileHandler
from spotipy.oauth2 import SpotifyOAuth, SpotifyOauthError

from .config import Config, token_cache_path

SCOPES = [
    "user-read-currently-playing",
    "user-read-playback-state",
    "user-top-read",
    "user-read-recently-played",
]


class TokenStatus(Enum):
    VALID = "valid"
    MISSING = "missing"
    # Spotify refresh tokens die 6 months after the original authorization.
    EXPIRED = "expired"


def make_oauth(config: Config) -> SpotifyOAuth:
    cache_path = token_cache_path()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    return SpotifyOAuth(
        client_id=config.client_id,
        client_secret=config.client_secret,
        redirect_uri=config.redirect_uri,
        scope=SCOPES,
        cache_handler=CacheFileHandler(cache_path=str(cache_path)),
        open_browser=True,
        requests_timeout=15,
    )


def check_token(oauth: SpotifyOAuth) -> TokenStatus:
    """Validate the cached token, silently refreshing it when possible."""
    cached = oauth.cache_handler.get_cached_token()
    if not cached:
        return TokenStatus.MISSING
    try:
        # Refreshes the access token when it's expired.
        token = oauth.validate_token(cached)
    except SpotifyOauthError:
        # invalid_grant: the refresh token itself is dead (revoked or past its 6-month lifetime).
        logout()
        return TokenStatus.EXPIRED
    except requests.RequestException:
        # Offline: keep the token, the app will surface the network error itself.
        return TokenStatus.VALID
    if token is None:
        # Cached token was granted with fewer scopes than we need now.
        logout()
        return TokenStatus.MISSING
    return TokenStatus.VALID


def login(oauth: SpotifyOAuth) -> None:
    """Open the browser on Spotify's consent page and wait for the local callback."""
    oauth.get_access_token(as_dict=False, check_cache=False)


def logout() -> bool:
    """Delete the cached token. Returns True if there was one."""
    path = token_cache_path()
    if path.exists():
        path.unlink()
        return True
    return False
