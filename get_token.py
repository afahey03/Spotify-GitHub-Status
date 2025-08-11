import webbrowser
import requests
import base64
import urllib.parse
from dotenv import load_dotenv
import os

load_dotenv()

CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

if not CLIENT_ID or not CLIENT_SECRET:
    print("❌ ERROR: SPOTIFY_CLIENT_ID or SPOTIFY_CLIENT_SECRET not found in .env file!")
    print("\nMake sure your .env file contains:")
    print("SPOTIFY_CLIENT_ID=your_client_id_here")
    print("SPOTIFY_CLIENT_SECRET=your_client_secret_here")
    exit(1)

REDIRECT_OPTIONS = [
    "https://example.com/callback"
]

print("=" * 70)
print("SPOTIFY TOKEN GETTER - QUICK FIX")
print("=" * 70)
print(f"\n✅ Found Client ID: {CLIENT_ID[:8]}...")
print(f"✅ Found Client Secret: {CLIENT_SECRET[:8]}...")

print("\n🔍 Which redirect URI is registered in your Spotify app?")
print("   (Check at https://developer.spotify.com/dashboard → Your App → Settings)\n")

for i, uri in enumerate(REDIRECT_OPTIONS, 1):
    print(f"{i}. {uri}")
print(f"{len(REDIRECT_OPTIONS) + 1}. Enter a custom URI")

choice = input(f"\nEnter your choice (1-{len(REDIRECT_OPTIONS) + 1}): ").strip()

try:
    choice_idx = int(choice) - 1
    if choice_idx < len(REDIRECT_OPTIONS):
        REDIRECT_URI = REDIRECT_OPTIONS[choice_idx]
    else:
        REDIRECT_URI = input("Enter your custom redirect URI: ").strip()
except:
    print("Invalid choice, using default")
    REDIRECT_URI = REDIRECT_OPTIONS[0]

print(f"\n📌 Using redirect URI: {REDIRECT_URI}")

SCOPE = "user-read-currently-playing user-read-playback-state"

auth_url = f"https://accounts.spotify.com/authorize"
params = {
    "client_id": CLIENT_ID,
    "response_type": "code",
    "redirect_uri": REDIRECT_URI,
    "scope": SCOPE,
    "show_dialog": "true"
}

full_auth_url = f"{auth_url}?{urllib.parse.urlencode(params)}"

print("\n" + "=" * 70)
print("STEP 1: OPENING SPOTIFY AUTHORIZATION")
print("=" * 70)

print("\n🌐 Opening your browser now...")
print("   If it doesn't open, copy this URL manually:\n")
print(full_auth_url)
print("\n" + "-" * 70)

webbrowser.open(full_auth_url)

print("\n📋 After clicking 'Agree' in Spotify:")
print("   1. You'll be redirected (the page might not load - that's OK!)")
print("   2. Copy the ENTIRE URL from your browser's address bar")
print(f"   3. It should start with: {REDIRECT_URI}?code=...")

print("\n" + "=" * 70)
print("STEP 2: PASTE THE URL")
print("=" * 70)

full_url = input("\n📋 Paste the complete URL here and press Enter:\n→ ").strip()

try:
    if "code=" in full_url:
        parsed = urllib.parse.urlparse(full_url)
        params = urllib.parse.parse_qs(parsed.query)
        auth_code = params.get('code', [None])[0]
        
        if not auth_code:
            print("❌ Couldn't find code in URL")
            exit(1)
            
        print(f"\n✅ Got authorization code: {auth_code[:30]}...")
    else:
        print("❌ No 'code' parameter found in the URL.")
        print("   Make sure you copied the entire URL including the ?code=... part")
        exit(1)
except Exception as e:
    print(f"❌ Error parsing URL: {e}")
    exit(1)

print("\n" + "=" * 70)
print("STEP 3: GETTING YOUR REFRESH TOKEN")
print("=" * 70)

token_url = "https://accounts.spotify.com/api/token"

auth_str = f"{CLIENT_ID}:{CLIENT_SECRET}"
b64_auth = base64.b64encode(auth_str.encode()).decode()

headers = {
    "Authorization": f"Basic {b64_auth}",
    "Content-Type": "application/x-www-form-urlencoded"
}

data = {
    "grant_type": "authorization_code",
    "code": auth_code,
    "redirect_uri": REDIRECT_URI
}

print("\n🔄 Exchanging code for tokens...")
response = requests.post(token_url, headers=headers, data=data)

if response.status_code == 200:
    tokens = response.json()
    refresh_token = tokens.get('refresh_token')
    
    if not refresh_token:
        print("❌ No refresh token received. This might happen if you're re-using an old code.")
        print("   Please run the script again with a fresh authorization.")
        exit(1)
    
    print("\n" + "=" * 70)
    print("🎉 SUCCESS!")
    print("=" * 70)
    
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    
    print(f"\n📝 Updating your .env file at:\n   {env_path}")
    
    try:
        env_lines = []
        if os.path.exists(env_path):
            with open(env_path, 'r') as f:
                env_lines = f.readlines()
        
        token_updated = False
        for i, line in enumerate(env_lines):
            if line.startswith('SPOTIFY_REFRESH_TOKEN='):
                env_lines[i] = f'SPOTIFY_REFRESH_TOKEN={refresh_token}\n'
                token_updated = True
                break
        
        if not token_updated:
            env_lines.append(f'SPOTIFY_REFRESH_TOKEN={refresh_token}\n')
        
        with open(env_path, 'w') as f:
            f.writelines(env_lines)
        
        print("✅ Successfully updated SPOTIFY_REFRESH_TOKEN in .env file!")
        print("\n🎵 You can now run your main script:")
        print("   python spotifygithub.py")
        
    except Exception as e:
        print(f"\n⚠️  Couldn't automatically update .env file: {e}")
        print("\n📋 Please manually add this to your .env file:")
        print(f"\nSPOTIFY_REFRESH_TOKEN={refresh_token}\n")
    
else:
    print(f"\n❌ Failed to get tokens!")
    print(f"Status: {response.status_code}")
    
    try:
        error_data = response.json()
        error = error_data.get('error', 'unknown')
        desc = error_data.get('error_description', '')
        
        print(f"Error: {error}")
        print(f"Description: {desc}")
        
        if error == 'invalid_grant':
            print("\n🔧 The authorization code expired or was already used.")
            print("   → Run this script again and paste the URL quickly (codes expire in 30 seconds)")
        elif error == 'invalid_client':
            print("\n🔧 Your Client ID or Client Secret is incorrect.")
            print("   → Check your .env file and Spotify app settings")
        elif error == 'redirect_uri_mismatch':
            print(f"\n🔧 The redirect URI doesn't match what's in your Spotify app.")
            print(f"   → Make sure '{REDIRECT_URI}' is added to your app's Redirect URIs")
            
    except:
        print(f"Raw response: {response.text}")
        

print("\n" + "=" * 70)
