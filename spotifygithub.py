import os
import time
import logging
from datetime import datetime, timedelta, timezone
import sys
import requests
import re
from dotenv import load_dotenv

load_dotenv()

ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REFRESH_TOKEN = os.getenv("SPOTIFY_REFRESH_TOKEN")

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "15"))
STATUS_PREFIX = os.getenv("STATUS_PREFIX", "🎵 ")
CLEAR_STATUS_WHEN_IDLE = os.getenv("CLEAR_STATUS_WHEN_IDLE", "true").lower() in ("1", "true", "yes")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(message)s")

GITHUB_GRAPHQL = "https://api.github.com/graphql"


def update_env_file(key, value):
    """Update a key in the .env file."""
    try:
        if os.path.exists(ENV_PATH):
            with open(ENV_PATH, 'r') as file:
                lines = file.readlines()
            
            updated = False
            for i, line in enumerate(lines):
                if line.startswith(f"{key}="):
                    lines[i] = f"{key}={value}\n"
                    updated = True
                    break
            
            if not updated:
                lines.append(f"{key}={value}\n")
            
            with open(ENV_PATH, 'w') as file:
                file.writelines(lines)
            
            logging.info(f"Updated {key} in .env file")
            
            os.environ[key] = value
            return True
        else:
            logging.error(".env file not found at %s", ENV_PATH)
            return False
    except Exception as e:
        logging.error("Failed to update .env file: %s", e)
        return False


def refresh_access_token():
    """Refresh Spotify access token using the stored refresh token."""
    global SPOTIFY_REFRESH_TOKEN
    
    url = "https://accounts.spotify.com/api/token"
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": SPOTIFY_REFRESH_TOKEN,
        "client_id": SPOTIFY_CLIENT_ID,
        "client_secret": SPOTIFY_CLIENT_SECRET,
    }
    
    try:
        r = requests.post(url, data=payload)
        if r.status_code != 200:
            logging.error("Failed to refresh access token: %s %s", r.status_code, r.text)
            
            if r.status_code == 400:
                error_data = r.json()
                if error_data.get("error") == "invalid_grant":
                    logging.error("Refresh token has expired! You need to re-authenticate.")
                    logging.error("Run the OAuth helper script again to get a new refresh token.")
                    return None
            return None
            
        data = r.json()
        access_token = data.get("access_token")
        expires_in = data.get("expires_in", 3600)
        
        new_refresh_token = data.get("refresh_token")
        if new_refresh_token and new_refresh_token != SPOTIFY_REFRESH_TOKEN:
            logging.info("Spotify provided a new refresh token, updating .env file...")
            if update_env_file("SPOTIFY_REFRESH_TOKEN", new_refresh_token):
                SPOTIFY_REFRESH_TOKEN = new_refresh_token
                logging.info("Successfully updated refresh token in .env file")
            else:
                logging.warning("Failed to update refresh token in .env file, using new token for this session only")
                SPOTIFY_REFRESH_TOKEN = new_refresh_token
        
        return {
            "access_token": access_token, 
            "expires_at": datetime.utcnow() + timedelta(seconds=expires_in)
        }
    except Exception as e:
        logging.error("Exception during token refresh: %s", e)
        return None


def get_current_playing(access_token):
    """Fetch currently playing track from Spotify."""
    url = "https://api.spotify.com/v1/me/player/currently-playing"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    try:
        r = requests.get(url, headers=headers)
        if r.status_code == 204:
            return None
        if r.status_code == 401:
            logging.warning("Access token expired or invalid")
            return "TOKEN_EXPIRED"
        if r.status_code != 200:
            logging.warning("Spotify API returned %s %s", r.status_code, r.text)
            return None

        data = r.json()
        if not data.get("item") or not data.get("is_playing", False):
            return None

        name = data["item"]["name"]
        artists = ", ".join(a["name"] for a in data["item"]["artists"])
        message = f"{STATUS_PREFIX}{name} by {artists}"

        progress_ms = data.get("progress_ms", 0)
        duration_ms = data["item"].get("duration_ms", 0)
        remaining_ms = max(duration_ms - progress_ms, 0)

        expires_at = datetime.now(timezone.utc) + timedelta(milliseconds=remaining_ms)

        return {"message": message, "expires_at": expires_at}
    except Exception as e:
        logging.error("Exception during Spotify API call: %s", e)
        return None


def set_github_status(message, expires_at=None):
    """Update GitHub profile status with optional expiry."""
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
    
    try:
        if message is None:
            query = """
            mutation {
              changeUserStatus(input: { message: "" }) {
                status { message expiresAt }
              }
            }
            """
            variables = {}
        else:
            query = """
            mutation($message: String!, $expiresAt: DateTime) {
              changeUserStatus(input: { message: $message, expiresAt: $expiresAt }) {
                status { message expiresAt }
              }
            }
            """
            variables = {
                "message": message, 
                "expiresAt": expires_at.isoformat() if expires_at else None
            }

        r = requests.post(GITHUB_GRAPHQL, json={"query": query, "variables": variables}, headers=headers)
        if r.status_code != 200:
            logging.error("Failed to update GitHub status: %s", r.text)
            return False
        
        response_data = r.json()
        if "errors" in response_data:
            logging.error("GraphQL errors: %s", response_data["errors"])
            return False

        logging.info("GitHub status updated to: %s (expires %s)", 
                    message if message else "<cleared>", expires_at)
        return True
    except Exception as e:
        logging.error("Exception during GitHub API call: %s", e)
        return False


def main():
    """Main loop with automatic token refresh and .env updates."""
    access_token = None
    expires_at_token = datetime.utcnow()
    last_status = None
    consecutive_failures = 0
    max_failures = 5

    logging.info("Starting Spotify-GitHub status updater...")
    logging.info("Using .env file at: %s", ENV_PATH)

    while True:
        try:
            if not access_token or datetime.utcnow() >= expires_at_token - timedelta(seconds=60):
                logging.debug("Refreshing Spotify access token...")
                token_data = refresh_access_token()
                
                if not token_data:
                    consecutive_failures += 1
                    if consecutive_failures >= max_failures:
                        logging.error("Failed to refresh token %d times. Exiting.", max_failures)
                        logging.error("Please run the OAuth helper script to get a new refresh token.")
                        sys.exit(1)
                    
                    wait_time = min(POLL_INTERVAL * consecutive_failures, 300)
                    logging.warning("Failed to refresh token (attempt %d/%d), retrying in %s seconds", 
                                  consecutive_failures, max_failures, wait_time)
                    time.sleep(wait_time)
                    continue
                
                access_token = token_data["access_token"]
                expires_at_token = token_data["expires_at"]
                consecutive_failures = 0

            track_info = get_current_playing(access_token)
            
            if track_info == "TOKEN_EXPIRED":
                logging.info("Token expired, forcing refresh...")
                access_token = None
                continue
            
            if track_info:
                status_message = track_info["message"]
                status_expires = track_info["expires_at"]
            else:
                status_message = None
                status_expires = None

            if status_message != last_status:
                if status_message is None and not CLEAR_STATUS_WHEN_IDLE:
                    logging.debug("Nothing playing; skipping clear.")
                else:
                    if set_github_status(status_message, status_expires):
                        last_status = status_message

            time.sleep(POLL_INTERVAL)
            
        except KeyboardInterrupt:
            logging.info("Received interrupt signal, cleaning up...")
            if CLEAR_STATUS_WHEN_IDLE:
                logging.info("Clearing GitHub status...")
                set_github_status(None)
            break
        except Exception as e:
            logging.error("Unexpected error in main loop: %s", e)
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    missing = []
    if not SPOTIFY_CLIENT_ID:
        missing.append("SPOTIFY_CLIENT_ID")
    if not SPOTIFY_CLIENT_SECRET:
        missing.append("SPOTIFY_CLIENT_SECRET")
    if not SPOTIFY_REFRESH_TOKEN:
        missing.append("SPOTIFY_REFRESH_TOKEN")
    if not GITHUB_TOKEN:
        missing.append("GITHUB_TOKEN")
    
    if missing:
        logging.error("Missing required environment variables: %s", ", ".join(missing))
        logging.error("Please check your .env file at: %s", ENV_PATH)
        sys.exit(1)
    
    try:
        main()
    except Exception as e:
        logging.error("Fatal error: %s", e)

        sys.exit(1)
