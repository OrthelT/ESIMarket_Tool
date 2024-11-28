import json
import os
import time
import webbrowser
from requests_oauthlib import OAuth2Session
from dotenv import load_dotenv

# Environment set up. Here we gather the environment information to request an Oauth token. Note that we're using
# insecure transport. This tells the Eve SSO that we want to use standard HTTP:// rather than HTTPS:// to login.
# This is so we can use a http://localhost:8000 connection for development without setting up a HTTPS:// server.
# This should be used for development purpose only. HTTPS:// should be used in production instead.
load_dotenv()
os.environ[
    'OAUTHLIB_INSECURE_TRANSPORT'] = '1'  # to allow us to use localhost for development. Use HTTPS:// in production.
CLIENT_ID = os.getenv('CLIENT_ID')  # stored in you .env file
SECRET_KEY = os.getenv('SECRET_KEY')  # stored in you .env file
REDIRECT_URI = 'http://localhost:8000/callback'  # workaround so we don't have to set up a real server
AUTHORIZATION_URL = 'https://login.eveonline.com/v2/oauth/authorize'
TOKEN_URL = 'https://login.eveonline.com/v2/oauth/token'
token_file = 'token.json'
# ------------------------------------------------
# Functions: Oauth2 Flow
# -----------------------------------------------
# call this function from other programs to get an ESI token
def get_token(requested_scope: str | list[str]) -> dict | None:
    """
    Retrieve a token, refreshing it using the refresh token if available.
    This function attempts to load an existing token and checks if it is still valid. If the token is
    expired, it refreshes the token using the refresh token and saves the new token. If no existing
    token is found, it initiates the process to obtain a new authorization code.

    :param requested_scope: The scope for which the token is being requested. It can be a single
                            scope represented as a string or multiple scopes represented as a list.
    :return: A dictionary containing the token information if successful, or None if a new
             authorization code is needed.
    examples:
    get_token('esi-wallet.read_corporation_wallet.v1')
    get_token(['esi-wallet.read_corporation_wallet.v1', 'esi-assets.read_corporation_assets.v1'])
    """
    print('opening ESI session...')
    print('----------------------------------')
    print(f'requested scope: {requested_scope}')
    print('----------------------------------')

    token = load_token()  # first we try to get a token if we already have one, if not we'll go get one.

    if token:
        oauth = get_oauth_session(token, requested_scope)
        expire = oauth.token['expires_at']  # if your token is expired, we refresh it
        print(f'token expires at {expire}')
        if expire < time.time():
            print("Token expired, refreshing token...")
            token = oauth.refresh_token(TOKEN_URL, client_id=CLIENT_ID, client_secret=SECRET_KEY)
            print('saving new token')
            save_token(token)
        print('returning token')
        return token
    else:
        print('need to get an authorization code, stand by')
        return get_authorization_code(token=None,
                                      requested_scope=requested_scope)  # first time here? np, we will get you a token by logging into the Eve SSO
        #You will just refresh this token for future requests.

def load_token():
    # Load the OAuth token from a file, if it exists.
    if os.path.exists(token_file):
        print('loading token...')
        with open(token_file, 'r') as f:
            return json.load(f)  # got a token?
    return None  # no token? no problem, we'll go get one.


# Redirects you to the EVE Online login page to get the authorization code.

def get_authorization_code(token=None, requested_scope=None):
    oauth = get_oauth_session(token=None, requested_scope=requested_scope)
    print(
        f"Opening browser to log in with Eve SSO. Please authorize access to the following scopes: {requested_scope}"
    )
    authorization_url, state = oauth.authorization_url(AUTHORIZATION_URL)
    print(f"Please go to this URL and authorize access: {authorization_url}")
    webbrowser.open(authorization_url)
    redirect_response = input('Paste the full redirect URL here: ')
    token = oauth.fetch_token(TOKEN_URL, authorization_response=redirect_response, client_secret=SECRET_KEY)
    save_token(token)
    return token


def get_oauth_session(token=None, requested_scope=None):
    # Get an OAuth session, refreshing the token if necessary.
    # Finally, we can open an Oath session.
    print(f'opening Oauth session...SCOPE: {requested_scope}')
    extra = {'client_id': CLIENT_ID, 'client_secret': SECRET_KEY}
    if token:
        return OAuth2Session(CLIENT_ID, token=token, auto_refresh_url=TOKEN_URL, auto_refresh_kwargs=extra,
                             token_updater=save_token)
    else:
        return OAuth2Session(CLIENT_ID, redirect_uri=REDIRECT_URI, scope=requested_scope)


def save_token(token):
    # Save the OAuth token, including refresh token to a file.
    print('saving token...')
    with open(token_file, 'w') as f:
        json.dump(token, f)
        # note some IDEs will flag this as an error.
        # This is because jason.dump expects a str, but got a TextIO instead.
        # TextIO does support string writing, so this is not actually an issue.
    print('token saved')
