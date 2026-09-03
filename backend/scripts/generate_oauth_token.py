"""One-time helper to authorize a Google user and store an OAuth token.

Run this ONCE on your host (not inside Docker, since it opens a browser):

    cd backend
    python -m pip install google-auth-oauthlib
    python scripts/generate_oauth_token.py

Prerequisites:
- In Google Cloud Console > APIs & Services > Credentials, create an OAuth
  client ID of type "Desktop app" and download its JSON.
- Save it as backend/oauth-client-secrets.json.
- The Google Drive API must be enabled for the project.
- Add your Google account as a "Test user" on the OAuth consent screen while it
  is in "Testing" mode.

The script opens a browser, asks you to grant Drive access, and writes the
resulting token (including a long-lived refresh token) to backend/oauth-token.json.
The backend then uses that token to upload files under YOUR Drive quota.

Note: this script is intentionally self-contained and does NOT import the app
package, so it only needs `google-auth-oauthlib` installed on the host - not the
full backend dependency set.
"""
import os

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/drive"]

# Resolve paths relative to the backend directory (parent of this scripts dir),
# so the script works no matter where it's invoked from.
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Allow overrides via env vars, but strip container-style "/app/..." paths since
# those don't exist on the host; fall back to files in the backend directory.
def _host_path(env_value: str | None, default_name: str) -> str:
    if env_value and not env_value.startswith("/app/") and os.path.isabs(env_value):
        return env_value
    return os.path.join(_BACKEND_DIR, default_name)


def main() -> None:
    client_secrets = _host_path(
        os.environ.get("GOOGLE_OAUTH_CLIENT_SECRETS"), "oauth-client-secrets.json"
    )
    token_path = _host_path(
        os.environ.get("GOOGLE_OAUTH_TOKEN_PATH"), "oauth-token.json"
    )

    if not os.path.exists(client_secrets):
        raise SystemExit(
            f"OAuth client secrets not found at '{client_secrets}'. Download a "
            "Desktop-app OAuth client JSON from Google Cloud Console and save it "
            "as backend/oauth-client-secrets.json."
        )

    flow = InstalledAppFlow.from_client_secrets_file(client_secrets, SCOPES)
    # access_type=offline + prompt=consent guarantees we receive a refresh token.
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

    with open(token_path, "w", encoding="utf-8") as fh:
        fh.write(creds.to_json())

    print(f"Success. Token written to: {token_path}")
    print(
        "The docker-compose bind mount exposes backend/ at /app, so the backend "
        "will read it at /app/oauth-token.json. Restart the backend: "
        "docker compose restart backend"
    )


if __name__ == "__main__":
    main()
