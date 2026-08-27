import os, sys, pickle
sys.stdout.reconfigure(line_buffering=True)
from google_auth_oauthlib.flow import InstalledAppFlow

os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'

CLIENT_SECRETS_FILE = os.path.join(os.path.dirname(__file__), '..', 'client_secret.json')
ACCOUNTS_DIR = os.path.join(os.path.dirname(__file__), '..', 'accounts')
TOKEN_FILE = os.path.join(ACCOUNTS_DIR, 'lol_token.pickle')

SCOPES = [
    'https://www.googleapis.com/auth/youtube.readonly',
    'https://www.googleapis.com/auth/youtube.upload',
    'https://www.googleapis.com/auth/yt-analytics.readonly',
    'https://www.googleapis.com/auth/youtube.force-ssl',
]

def main():
    flow = InstalledAppFlow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
    )

    credentials = flow.run_local_server(
        port=8080,
        prompt='consent select_account',
        authorization_prompt_message='AUTH_LINK_START\n{url}\nAUTH_LINK_END',
        open_browser=False
    )

    os.makedirs(ACCOUNTS_DIR, exist_ok=True)
    with open(TOKEN_FILE, 'wb') as f:
        pickle.dump(credentials, f)

    print(f'SUCCESS: {TOKEN_FILE}', flush=True)

if __name__ == '__main__':
    main()
