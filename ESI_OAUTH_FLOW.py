import json
import logging
import os
import time
import webbrowser
from pathlib import Path

from requests_oauthlib import OAuth2Session

logger = logging.getLogger(__name__)

REDIRECT_URI = 'http://localhost:8000/callback'
AUTHORIZATION_URL = 'https://login.eveonline.com/v2/oauth/authorize'
TOKEN_URL = 'https://login.eveonline.com/v2/oauth/token'


def get_token(
    client_id: str,
    secret_key: str,
    requested_scope: str | list[str],
    token_path: Path = Path("token.json"),
) -> dict | None:
    """Retrieve a token, refreshing if available, or initiate OAuth flow.

    Args:
        client_id: EVE SSO application client ID
        secret_key: EVE SSO application secret key
        requested_scope: Scope(s) for the token request
        token_path: Path to the token cache file

    Returns:
        Token dict if successful, None if authorization fails
    """
    logger.info('Opening ESI session...')
    logger.info(f'Requested scope: {requested_scope}')

    token = _load_token(token_path)

    if token:
        oauth = _get_oauth_session(client_id, secret_key, token, requested_scope)
        expire = oauth.token['expires_at']
        logger.info(f'Token expires at {expire}')
        if expire < time.time():
            logger.info("Token expired, refreshing...")
            token = oauth.refresh_token(TOKEN_URL, client_id=client_id, client_secret=secret_key)
            _save_token(token, token_path)
        return token
    else:
        logger.info('No existing token found, starting authorization flow')
        return _get_authorization_code(
            client_id=client_id,
            secret_key=secret_key,
            requested_scope=requested_scope,
            token_path=token_path,
        )


def _load_token(token_path: Path) -> dict | None:
    """Load the OAuth token from a file, if it exists."""
    if token_path.exists():
        logger.info('Loading token...')
        with open(token_path, 'r') as f:
            return json.load(f)
    return None


def _get_authorization_code(
    client_id: str,
    secret_key: str,
    requested_scope: str | list[str],
    token_path: Path,
) -> dict:
    """Open browser for EVE SSO login and capture the authorization code."""
    oauth = _get_oauth_session(client_id, secret_key, token=None, requested_scope=requested_scope)
    authorization_url, state = oauth.authorization_url(AUTHORIZATION_URL)
    print(f"Opening browser for EVE SSO login. Please authorize the requested scopes.")
    logger.info(f"Authorization URL: {authorization_url}")
    webbrowser.open(authorization_url)
    redirect_response = input('Paste the full redirect URL here: ')
    token = oauth.fetch_token(TOKEN_URL, authorization_response=redirect_response, client_secret=secret_key)
    _save_token(token, token_path)
    return token


def _get_oauth_session(
    client_id: str,
    secret_key: str,
    token: dict | None = None,
    requested_scope: str | list[str] | None = None,
) -> OAuth2Session:
    """Get an OAuth session, optionally with an existing token for auto-refresh."""
    extra = {'client_id': client_id, 'client_secret': secret_key}
    if token:
        return OAuth2Session(
            client_id,
            token=token,
            auto_refresh_url=TOKEN_URL,
            auto_refresh_kwargs=extra,
            token_updater=lambda t: _save_token(t, Path("token.json")),
        )
    else:
        return OAuth2Session(client_id, redirect_uri=REDIRECT_URI, scope=requested_scope)


def _save_token(token: dict, token_path: Path) -> None:
    """Save the OAuth token to a file."""
    logger.info('Saving token...')
    with open(token_path, 'w') as f:
        json.dump(token, f)
    logger.info('Token saved')


if __name__ == '__main__':
    pass
