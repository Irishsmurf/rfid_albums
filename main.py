import base64
import json
import os
import time
import hashlib
import requests
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore

# --- Configuration ---
# These should be set as environment variables in the Cloud Function
LASTFM_API_KEY = os.environ.get("LASTFM_API_KEY", "YOUR_LASTFM_API_KEY_PLACEHOLDER")
LASTFM_API_SECRET = os.environ.get("LASTFM_API_SECRET", "YOUR_LASTFM_SECRET_PLACEHOLDER")
# APP_ID is your Firebase Project ID. This environment variable MUST be set to your
# Firebase Project ID (e.g., "my-firebase-project-12345").
# This ID is used to construct the correct paths for accessing data within Firestore.
# The original rfid_reader.py script also used an APP_ID variable; this should match that value.
APP_ID = os.environ.get("APP_ID")

LASTFM_API_URL = "http://ws.audioscrobbler.com/2.0/"

# Initialize Firebase Admin SDK
# In a Cloud Function environment, if the function has the correct IAM permissions,
# credentials don't need to be explicitly passed if using default service account.
# For local testing, set GOOGLE_APPLICATION_CREDENTIALS environment variable.
try:
    firebase_admin.initialize_app()
    db = firestore.client()
    print("Firebase Admin SDK initialized successfully.")
except Exception as e:
    print(f"Error initializing Firebase Admin SDK: {e}")
    db = None

# --- Helper Functions ---

def get_lastfm_session_key():
    """Retrieves the Last.fm session key from Firestore."""
    if not db:
        print("Firestore client not available.")
        return None
    if not APP_ID:
        print("APP_ID (Firebase Project ID) environment variable not set.")
        return None

    # Path matches the one used in the original web application:
    # Collection: artifacts/{APP_ID}/private/data
    # Document ID: lastFmSessionKey
    # Field in Document: 'key' (string)
    # User should verify that 'index.html' stores the session key in a field named 'key'.
    doc_ref = db.collection(f'artifacts/{APP_ID}/private/data').document('lastFmSessionKey')
    try:
        doc = doc_ref.get()
        if doc.exists:
            session_key_data = doc.to_dict()
            session_key = session_key_data.get('key')
            if session_key:
                print("Successfully retrieved Last.fm session key.")
                return session_key
            else:
                print(f"Error: 'key' field not found in lastFmSessionKey document. Fields found: {list(session_key_data.keys()) if session_key_data else 'None'}")
                return None
        else:
            print(f"Error: Last.fm session key document not found at path: artifacts/{APP_ID}/private/data/lastFmSessionKey")
            return None
    except Exception as e:
        print(f"Error getting Last.fm session key from Firestore: {e}")
        return None

def get_album_details_from_rfid(rfid_tag):
    """Retrieves album artist and title from Firestore using RFID tag."""
    if not db:
        print("Firestore client not available.")
        return None, None
    if not APP_ID:
        print("APP_ID (Firebase Project ID) environment variable not set.")
        return None, None

    # Path matches the one used in the original web application:
    # Collection: artifacts/{APP_ID}/public/data/albums
    # Document ID: {RFID_TAG_ID} (the scanned RFID tag)
    # Fields in Document: 'artist' (string), 'albumName' (string)
    # User should verify that 'index.html' stores these fields with these exact names.
    doc_ref = db.collection(f'artifacts/{APP_ID}/public/data/albums').document(rfid_tag)
    try:
        doc = doc_ref.get()
        if doc.exists:
            data = doc.to_dict()
            artist = data.get('artist')
            album_title = data.get('albumName') # Based on README context and common usage
            if artist and album_title:
                print(f"Found album for RFID {rfid_tag}: {album_title} by {artist}")
                return artist, album_title
            else:
                missing_fields = []
                if not artist: missing_fields.append("'artist'")
                if not album_title: missing_fields.append("'albumName'")
                print(f"Error: Fields {', '.join(missing_fields)} missing in Firestore document for RFID {rfid_tag} at path artifacts/{APP_ID}/public/data/albums/{rfid_tag}. Fields found: {list(data.keys())}")
                return None, None
        else:
            print(f"Error: No album mapping document found for RFID {rfid_tag} at path: artifacts/{APP_ID}/public/data/albums/{rfid_tag}")
            return None, None
    except Exception as e:
        print(f"Error getting album details from Firestore: {e}")
        return None, None

def generate_api_signature(params, secret):
    """Generates MD5 signature for Last.fm API calls."""
    # Sort parameters alphabetically by key
    sorted_params = sorted(params.items())
    # Concatenate key-value pairs
    param_string = "".join([f"{k}{v}" for k, v in sorted_params])
    # Append API secret
    param_string += secret
    # MD5 hash
    return hashlib.md5(param_string.encode('utf-8')).hexdigest()

def get_album_tracks(artist, album, api_key):
    """Fetches track list for an album from Last.fm."""
    params = {
        'method': 'album.getinfo',
        'artist': artist,
        'album': album,
        'api_key': api_key,
        'format': 'json'
    }
    try:
        response = requests.get(LASTFM_API_URL, params=params)
        response.raise_for_status() # Raise an exception for bad status codes
        data = response.json()
        if 'album' in data and 'tracks' in data['album'] and 'track' in data['album']['tracks']:
            tracks = data['album']['tracks']['track']
            # Ensure tracks is a list (it's a single dict if only one track)
            if not isinstance(tracks, list):
                tracks = [tracks]
            track_names = [track['name'] for track in tracks if 'name' in track]
            print(f"Found {len(track_names)} tracks for '{album}' by {artist}.")
            return track_names
        else:
            error_message = data.get('message', 'Unknown error structure')
            print(f"Error: Could not parse tracks from Last.fm response for {artist} - {album}. Message: {error_message}")
            return []
    except requests.exceptions.RequestException as e:
        print(f"Error fetching album tracks from Last.fm: {e}")
        return []
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON response from Last.fm (album.getinfo): {e}")
        return []


def scrobble_track(session_key, artist, track, album, timestamp, api_key, api_secret):
    """Scrobbles a single track to Last.fm."""
    params = {
        'method': 'track.scrobble',
        'artist[0]': artist,
        'track[0]': track,
        'album[0]': album, # Optional but good to include
        'timestamp[0]': str(timestamp),
        'sk': session_key,
        'api_key': api_key,
        'format': 'json' # Request JSON response for easier parsing
    }
    # Parameters for API signature must not include 'format' or 'callback'
    sig_params = {k: v for k, v in params.items() if k not in ['format', 'callback']}
    api_sig = generate_api_signature(sig_params, api_secret)
    params['api_sig'] = api_sig

    try:
        response = requests.post(LASTFM_API_URL, data=params)
        response.raise_for_status()
        response_data = response.json()

        if 'scrobbles' in response_data and '@attr' in response_data['scrobbles'] and response_data['scrobbles']['@attr']['accepted'] == 1:
            print(f"Successfully scrobbled: {track} by {artist}")
            return True
        else:
            error_code = response_data.get('error', 'N/A')
            error_message = response_data.get('message', 'Scrobble not accepted or unknown error structure')
            print(f"Failed to scrobble {track}: Error {error_code} - {error_message}")
            if error_code == 9: # Session key not valid
                print("Session key might be invalid. User may need to re-authenticate via the web app.")
            return False
    except requests.exceptions.RequestException as e:
        print(f"Error scrobbling track to Last.fm: {e}")
        return False
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON response from Last.fm (track.scrobble): {e}")
        return False

# --- Main Cloud Function ---

def rfid_scrobbler_trigger(event, context):
    """
    Triggered by a Pub/Sub message.
    Processes an RFID tag scan for Last.fm scrobbling.
    """
    start_time = time.time()
    print(f"Cloud Function triggered by event ID: {context.event_id}, type: {context.event_type}")

    if not db:
        print("Critical: Firestore client not initialized. Exiting.")
        return 'Firestore client not initialized.', 500

    if not APP_ID:
        print("Critical: APP_ID (Firebase Project ID) environment variable not set. Exiting.")
        return 'APP_ID not set.', 500

    if not LASTFM_API_KEY or LASTFM_API_KEY == "YOUR_LASTFM_API_KEY_PLACEHOLDER" or \
       not LASTFM_API_SECRET or LASTFM_API_SECRET == "YOUR_LASTFM_SECRET_PLACEHOLDER":
        print("Critical: Last.fm API Key or Secret not configured. Exiting.")
        return 'Last.fm API credentials not set.', 500

    # Get RFID tag from Pub/Sub message
    if 'data' in event:
        try:
            rfid_tag = base64.b64decode(event['data']).decode('utf-8').strip()
            print(f"Received RFID Tag: {rfid_tag}")
        except Exception as e:
            print(f"Error decoding Pub/Sub message data: {e}")
            return f'Error decoding message data: {e}', 400
    else:
        print("No data in Pub/Sub event.")
        return 'No data in Pub/Sub event.', 400

    if not rfid_tag:
        print("Empty RFID tag received.")
        return 'Empty RFID tag.', 400

    # 1. Get Last.fm Session Key
    session_key = get_lastfm_session_key()
    if not session_key:
        print("Failed to retrieve Last.fm session key. Cannot scrobble.")
        # This is a configuration/setup issue, not necessarily a bad request.
        return 'Failed to get Last.fm session key.', 500

    # 2. Get Album Details for RFID Tag
    artist, album_title = get_album_details_from_rfid(rfid_tag)
    if not artist or not album_title:
        print(f"No album mapping found for RFID tag {rfid_tag}. Nothing to scrobble.")
        # This isn't an error for the function, just no action to take.
        return f'No album mapping for RFID {rfid_tag}.', 200 # OK, but no action

    # 3. Get Album Tracks from Last.fm
    tracks = get_album_tracks(artist, album_title, LASTFM_API_KEY)
    if not tracks:
        print(f"No tracks found for {album_title} by {artist}. Cannot scrobble.")
        return f'No tracks found for {album_title} by {artist}.', 200 # OK, but no action

    # 4. Scrobble Tracks
    # Last.fm requires timestamps in Unix UTC. Scrobbles should be in the past.
    # We'll simulate listening by starting from now and going backwards,
    # or starting some time ago and moving forwards.
    # For simplicity, let's start "now" and increment for each track.
    # Last.fm typically expects scrobbles for tracks you *finished* listening to.
    # A common pattern for album scrobbling is to timestamp them sequentially.
    # Let's assume an average track length of 3 minutes (180 seconds) for staggering.

    current_timestamp = int(time.time()) # Scrobble as "just finished"
    scrobbled_count = 0

    # Scrobble tracks in reverse order of how they appear on album for more natural "just finished"
    # Or, scrobble in order, with timestamps increasing from a start point.
    # The original web app "adjusted timestamps to reflect a typical album listening session."
    # Let's set the timestamp for the *first* track of the album to be ~ (num_tracks * avg_duration) ago,
    # and then each subsequent track is avg_duration later.

    avg_track_duration = 180 # seconds (3 minutes)
    album_duration_estimate = len(tracks) * avg_track_duration
    first_track_timestamp = current_timestamp - album_duration_estimate

    for i, track_name in enumerate(tracks):
        # Distribute scrobbles over the estimated album duration
        track_timestamp = first_track_timestamp + (i * avg_track_duration)

        # Ensure timestamp is not in the future (Last.fm might reject)
        # And not too far in the past (max 2 weeks)
        if track_timestamp > current_timestamp:
            track_timestamp = current_timestamp # Cap at current time

        print(f"Scrobbling track {i+1}/{len(tracks)}: '{track_name}' at timestamp {track_timestamp}")
        if scrobble_track(session_key, artist, track_name, album_title, track_timestamp, LASTFM_API_KEY, LASTFM_API_SECRET):
            scrobbled_count += 1
        else:
            print(f"Failed to scrobble track: {track_name}")
            # Decide if you want to stop on first error or try all tracks
            # For now, we try all tracks.

    end_time = time.time()
    print(f"Processing finished in {end_time - start_time:.2f} seconds.")
    if scrobbled_count == len(tracks) and len(tracks) > 0:
        return f'Successfully scrobbled {scrobbled_count} tracks for {album_title} by {artist}.', 200
    elif scrobbled_count > 0:
        return f'Partially scrobbled {scrobbled_count}/{len(tracks)} tracks for {album_title} by {artist}.', 200 # Or 207 Multi-Status
    elif len(tracks) == 0:
        return f'No tracks found to scrobble for {album_title} by {artist}.', 200
    else:
        return f'Failed to scrobble tracks for {album_title} by {artist}. Check logs.', 500

# For local testing (not used in Cloud Function deployment directly):
if __name__ == '__main__':
    # --- How to Test Locally ---
    # 1. Set Environment Variables:
    #    export GOOGLE_APPLICATION_CREDENTIALS="/path/to/your/serviceAccountKey.json"
    #    export APP_ID="your-firebase-project-id"
    #    export LASTFM_API_KEY="your_lastfm_api_key"
    #    export LASTFM_API_SECRET="your_lastfm_secret"
    #
    # 2. Ensure Firestore has:
    #    - A Last.fm session key at: artifacts/{APP_ID}/private/data/lastFmSessionKey (doc) with a 'key' field.
    #    - An album mapping for your test RFID tag at: artifacts/{APP_ID}/public/data/albums/{TEST_RFID_TAG} (doc)
    #      with 'artist' and 'albumName' fields.
    #
    # 3. Create a mock Pub/Sub event:
    print("Local test run started.")

    if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        print("WARNING: GOOGLE_APPLICATION_CREDENTIALS not set. Firestore operations will likely fail.")
    if not APP_ID:
         print("WARNING: APP_ID not set. Firestore operations will likely fail.")
    if LASTFM_API_KEY == "YOUR_LASTFM_API_KEY_PLACEHOLDER":
        print("WARNING: LASTFM_API_KEY not set. Last.fm operations will fail.")

    # Simulate a Pub/Sub event
    test_rfid_tag = "TEST_RFID_12345" # Replace with an RFID tag you have mapped in Firestore
    encoded_rfid_tag = base64.b64encode(test_rfid_tag.encode('utf-8')).decode('utf-8')

    mock_event = {
        'data': encoded_rfid_tag
    }
    mock_context = type('MockContext', (), {'event_id': 'local-test-event', 'event_type': 'pubsub.topic.publish'})()

    print(f"\n--- Simulating Cloud Function call with RFID: {test_rfid_tag} ---")
    response_message, status_code = rfid_scrobbler_trigger(mock_event, mock_context)
    print(f"--- Simulation Complete ---")
    print(f"Response: {response_message}")
    print(f"Status Code: {status_code}")

    # Example: Test get_lastfm_session_key directly
    # print("\n--- Testing get_lastfm_session_key ---")
    # sk = get_lastfm_session_key()
    # print(f"Session Key: {sk}")

    # Example: Test get_album_details_from_rfid directly
    # print("\n--- Testing get_album_details_from_rfid ---")
    # artist, album = get_album_details_from_rfid(test_rfid_tag)
    # print(f"Artist: {artist}, Album: {album}")

    # if artist and album:
    #     print("\n--- Testing get_album_tracks ---")
    #     tracks = get_album_tracks(artist, album, LASTFM_API_KEY)
    #     print(f"Tracks: {tracks}")

    #     if tracks and sk:
    #         print("\n--- Testing scrobble_track (first track only) ---")
    #         ts = int(time.time()) - 180 # 3 mins ago
    #         scrobble_track(sk, artist, tracks[0], album, ts, LASTFM_API_KEY, LASTFM_API_SECRET)
    # else:
    #     print(f"Cannot test track fetching or scrobbling as album details for {test_rfid_tag} were not found.")
    print("Local test run finished.")
