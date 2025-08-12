# Spotify-GitHub-Status
- A Python script that automatically updates your GitHub status to be what you are listening to on Spotify.
- Sort of a pain to get the refresh key, but once you have it you're good to go.

## What to do:
- Create a Spotify app and set your URI to "https://example.com/callback".
- Create a GitHub classic access token.
- Add a .env file and include fields for your Spotify client ID, client secret, refresh token, and GitHub token.
- Run get_token.py to update your .env with your refresh token.
- Run spotifygithub.py, and watch your status update.
- Optional: Set the script to run as a task in Windows task manager (or whatever the Mac or Linux equivalent is)
- Enjoy!
