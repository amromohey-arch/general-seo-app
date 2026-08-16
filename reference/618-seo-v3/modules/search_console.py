import os
import hashlib
import base64
import secrets
from datetime import datetime, timedelta

SCOPES = ['https://www.googleapis.com/auth/webmasters.readonly']
REDIRECT_URI = os.environ.get('REDIRECT_URI', 'http://localhost:5618/api/sc/callback')

# Store code verifier in memory (fine for single-user tool)
_code_verifier_store = {}

def _build_client_config():
    return {
        "web": {
            "client_id": os.environ.get('GOOGLE_CLIENT_ID', ''),
            "client_secret": os.environ.get('GOOGLE_CLIENT_SECRET', ''),
            "redirect_uris": [REDIRECT_URI],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }

def get_auth_url():
    import urllib.parse
    import urllib.request
    import json

    client_id = os.environ.get('GOOGLE_CLIENT_ID', '')
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b'=').decode()

    state = secrets.token_urlsafe(32)
    _code_verifier_store[state] = code_verifier

    params = {
        'client_id': client_id,
        'redirect_uri': REDIRECT_URI,
        'response_type': 'code',
        'scope': ' '.join(SCOPES),
        'access_type': 'offline',
        'prompt': 'consent',
        'state': state,
        'code_challenge': code_challenge,
        'code_challenge_method': 'S256',
    }
    auth_url = 'https://accounts.google.com/o/oauth2/auth?' + urllib.parse.urlencode(params)
    return auth_url, state


def exchange_code(code: str, state: str) -> dict:
    import urllib.parse
    import urllib.request
    import json

    code_verifier = _code_verifier_store.pop(state, None)
    client_id = os.environ.get('GOOGLE_CLIENT_ID', '')
    client_secret = os.environ.get('GOOGLE_CLIENT_SECRET', '')

    data = urllib.parse.urlencode({
        'code': code,
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': REDIRECT_URI,
        'grant_type': 'authorization_code',
        **(({'code_verifier': code_verifier}) if code_verifier else {}),
    }).encode()

    req = urllib.request.Request(
        'https://oauth2.googleapis.com/token',
        data=data,
        headers={'Content-Type': 'application/x-www-form-urlencoded'}
    )
    with urllib.request.urlopen(req) as resp:
        token_data = json.loads(resp.read())

    return {
        'token': token_data.get('access_token'),
        'refresh_token': token_data.get('refresh_token'),
        'token_uri': 'https://oauth2.googleapis.com/token',
        'client_id': client_id,
        'client_secret': client_secret,
        'scopes': SCOPES,
    }


def get_sc_keywords(token_data: dict, topic: str = None) -> list:
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = Credentials(
            token=token_data.get('token'),
            refresh_token=token_data.get('refresh_token'),
            token_uri=token_data.get('token_uri'),
            client_id=token_data.get('client_id'),
            client_secret=token_data.get('client_secret'),
            scopes=token_data.get('scopes', SCOPES),
        )
        service = build('searchconsole', 'v1', credentials=creds)
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
        body = {
            'startDate': start_date,
            'endDate': end_date,
            'dimensions': ['query'],
            'rowLimit': 500,
        }
        if topic:
            first_word = topic.strip().split()[0] if topic.strip() else 'video'
            body['dimensionFilterGroups'] = [{'filters': [{'dimension': 'query', 'operator': 'contains', 'expression': first_word}]}]
        response = service.searchanalytics().query(siteUrl='https://www.618media.com.au/', body=body).execute()
        rows = response.get('rows', [])
        return [row['keys'][0] for row in rows if row.get('impressions', 0) >= 3][:150]
    except Exception as e:
        print(f"[Search Console] Error: {e}")
        return []