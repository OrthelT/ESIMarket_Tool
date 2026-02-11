"""
OAuth2 authentication flow for EVE Online SSO.

Includes a lightweight HTTP callback server so users don't see a
'connection refused' error after authorizing in the browser.
"""

import http.server
import json
import logging
import threading
import time
import webbrowser
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from requests_oauthlib import OAuth2Session

logger = logging.getLogger(__name__)

REDIRECT_URI = 'http://localhost:8000/callback'
AUTHORIZATION_URL = 'https://login.eveonline.com/v2/oauth/authorize'
TOKEN_URL = 'https://login.eveonline.com/v2/oauth/token'

SUCCESS_HTML = """<!DOCTYPE html>
<html><head><title>ESI Market Tool</title>
<style>
  body { font-family: system-ui, sans-serif; display: flex; justify-content: center;
         align-items: center; height: 100vh; margin: 0; background: #1a1a2e; color: #eee; }
  .card { text-align: center; padding: 3em; border-radius: 12px;
          background: #16213e; box-shadow: 0 4px 20px rgba(0,0,0,0.3); }
  h1 { color: #4ecca3; margin-bottom: 0.5em; }
  p { color: #aaa; }
</style></head>
<body><div class="card">
  <h1>Authorization Successful!</h1>
  <p>You can close this tab and return to the terminal.</p>
</div></body></html>"""


def get_token(
    client_id: str,
    secret_key: str,
    requested_scope: str | list[str],
    token_path: Path = Path("token.json"),
    headless: bool = False,
) -> dict | None:
    """Retrieve a token, refreshing if available, or initiate OAuth flow.

    Args:
        client_id: EVE SSO application client ID
        secret_key: EVE SSO application secret key
        requested_scope: Scope(s) for the token request
        token_path: Path to the token cache file
        headless: If True, fail instead of opening a browser for initial auth

    Returns:
        Token dict if successful, None if authorization fails
    """
    logger.info('Opening ESI session...')
    logger.info(f'Requested scope: {requested_scope}')

    token = _load_token(token_path)

    if token:
        oauth = _get_oauth_session(client_id, secret_key, token, requested_scope, token_path)
        expire = oauth.token['expires_at']
        logger.info(f'Token expires at {expire}')
        if expire < time.time():
            logger.info("Token expired, refreshing...")
            token = oauth.refresh_token(TOKEN_URL, client_id=client_id, client_secret=secret_key)
            _save_token(token, token_path)
        return token
    else:
        if headless:
            logger.error("No existing token and running in headless mode. "
                         "Run interactively first to complete initial authorization.")
            return None
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


class _OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler that captures a single OAuth redirect and serves a success page."""

    redirect_url: str | None = None

    def do_GET(self) -> None:
        # Store the full redirect URL
        _OAuthCallbackHandler.redirect_url = f"http://localhost:8000{self.path}"
        # Serve success page
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(SUCCESS_HTML.encode())

    def log_message(self, format, *args) -> None:
        # Suppress default stderr logging; use our logger instead
        logger.debug(f"OAuth callback: {format % args}")


def _wait_for_callback(port: int = 8000, timeout: int = 120) -> str | None:
    """Start a one-shot HTTP server and wait for the OAuth callback.

    Returns the full redirect URL, or None on timeout.
    """
    _OAuthCallbackHandler.redirect_url = None

    server = http.server.HTTPServer(('localhost', port), _OAuthCallbackHandler)
    server.timeout = timeout

    # Run in a thread so we can implement a clean timeout
    def _serve():
        server.handle_request()  # Handle exactly one request

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()
    thread.join(timeout=timeout)

    server.server_close()
    return _OAuthCallbackHandler.redirect_url


def _get_authorization_code(
    client_id: str,
    secret_key: str,
    requested_scope: str | list[str],
    token_path: Path,
) -> dict:
    """Open browser for EVE SSO login and capture the authorization code.

    Starts a local HTTP server to automatically capture the redirect.
    Falls back to manual URL pasting if the server fails.
    """
    oauth = _get_oauth_session(client_id, secret_key, token=None, requested_scope=requested_scope, token_path=token_path)
    authorization_url, state = oauth.authorization_url(AUTHORIZATION_URL)

    print("Opening browser for EVE SSO login. Please authorize the requested scopes.")
    logger.info(f"Authorization URL: {authorization_url}")

    # Try to capture redirect automatically via callback server
    redirect_url = None
    try:
        webbrowser.open(authorization_url)
        print("Waiting for authorization (the browser should open automatically)...")
        redirect_url = _wait_for_callback(port=8000, timeout=120)
    except OSError as e:
        logger.warning(f"Could not start callback server: {e}")

    if not redirect_url:
        # Fallback: manual paste
        print("\nAutomatic capture failed or timed out.")
        redirect_url = input('Paste the full redirect URL here: ')

    token = oauth.fetch_token(TOKEN_URL, authorization_response=redirect_url, client_secret=secret_key)
    _save_token(token, token_path)
    return token


def _get_oauth_session(
    client_id: str,
    secret_key: str,
    token: dict | None = None,
    requested_scope: str | list[str] | None = None,
    token_path: Path = Path("token.json"),
) -> OAuth2Session:
    """Get an OAuth session, optionally with an existing token for auto-refresh."""
    extra = {'client_id': client_id, 'client_secret': secret_key}
    if token:
        return OAuth2Session(
            client_id,
            token=token,
            auto_refresh_url=TOKEN_URL,
            auto_refresh_kwargs=extra,
            token_updater=lambda t: _save_token(t, token_path),
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
