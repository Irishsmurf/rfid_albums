import serial
import time
import requests
import hashlib
import json

LASTFM_API_URL = "https://ws.audioscrobbler.com/2.0/"

def generate_api_signature(params, secret):
    """
    Generates a Last.fm API signature.
    Sorts parameters alphabetically, concatenates keys and values,
    appends the API secret, and returns the MD5 hash.
    """
    sorted_params = sorted(params.items())
    signature_string = "".join([f"{k}{v}" for k, v in sorted_params])
    signature_string += secret
    return hashlib.md5(signature_string.encode('utf-8')).hexdigest()

def make_lastfm_api_request(params, api_key, api_secret=None, session_key=None, http_method='GET'):
    """
    Makes a request to the Last.fm API.
    Handles API key, session key, signature generation, and HTTP method.
    Returns parsed JSON response or None on error.
    """
    # Add api_key to params
    params['api_key'] = api_key

    # Add session_key if provided
    if session_key:
        params['sk'] = session_key

    # Generate API signature if api_secret is provided
    if api_secret:
        # Signature is generated on params *before* adding 'format' or 'callback'
        api_sig = generate_api_signature({k: v for k, v in params.items() if k != 'format'}, api_secret)
        params['api_sig'] = api_sig

    # Add format=json to params (must be done after signature generation)
    params['format'] = 'json'

    try:
        if http_method.upper() == 'POST':
            response = requests.post(LASTFM_API_URL, data=params)
        else:
            response = requests.get(LASTFM_API_URL, params=params)

        response.raise_for_status() # Raises an HTTPError for bad responses (4XX or 5XX)

        # It's good practice to check content type before parsing JSON
        if 'application/json' in response.headers.get('Content-Type', ''):
            parsed_response = response.json()
            # Last.fm API specific error checking
            if 'error' in parsed_response:
                print(f"Last.fm API Error: {parsed_response.get('message', 'Unknown error')} (Code: {parsed_response.get('error', 'N/A')})")
                return None
            return parsed_response
        else:
            print(f"Error: Response was not JSON. Content: {response.text[:200]}...") # Log snippet of non-JSON response
            return None

    except requests.exceptions.HTTPError as e:
        print(f"HTTP Error: {e.response.status_code} - {e.response.reason}")
        print(f"Response content: {e.response.text[:200]}...") # Log snippet of error response
        return None
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"Failed to parse JSON response: {e}")
        print(f"Response content: {response.text[:200]}...") # Log snippet of problematic response
        return None
    except Exception as e: # Catch any other unexpected errors
        print(f"An unexpected error occurred during API request: {e}")
        return None

def log_to_firestore(db, app_id, message, type='info', details=None):
    """
    Writes a log entry to a dedicated Firestore collection.
    """
    if not db or not app_id:
        print(f"Firestore logging skipped: db or app_id not available (Message: {message})")
        return

    try:
        logs_collection_ref = db.collection(f'artifacts/{app_id}/public/data/script_logs')
        log_entry = {
            'timestamp': firestore.SERVER_TIMESTAMP,
            'message': message,
            'type': type,
            'source': 'rfid_script'
        }
        if details: # Optional dictionary for more structured data
            log_entry['details'] = details

        logs_collection_ref.add(log_entry)
        # Optional: print to console as well for local debugging
        # print(f"Firestore LOG ({type}): {message}")
    except Exception as e:
        print(f"ERROR: Failed to write log to Firestore: {e} (Original message: {message})")

def get_lastfm_config_from_firestore(db, app_id, user_id):
    """
    Fetches Last.fm API key, secret, and session key from Firestore.
    """
    log_message_start = f"Attempting to fetch Last.fm config for app '{app_id}', user '{user_id}'..."
    print(log_message_start)
    # log_to_firestore(db, app_id, log_message_start, type='info') # Logging this before db is confirmed might be an issue if this function is called before db init. Let's log specific outcomes.

    config_path = f'artifacts/{app_id}/users/{user_id}/config/lastfm'
    session_path = f'artifacts/{app_id}/users/{user_id}/config/lastfm_session'

    try:
        config_doc_ref = db.document(config_path)
        config_doc = config_doc_ref.get()

        session_doc_ref = db.document(session_path)
        session_doc = session_doc_ref.get()

        if not config_doc.exists:
            error_msg = f"Last.fm config document not found at '{config_path}'. Ensure authentication in web UI."
            print(f"ERROR: {error_msg}")
            log_to_firestore(db, app_id, error_msg, type='error', details={'path': config_path})
            return None

        if not session_doc.exists:
            error_msg = f"Last.fm session document not found at '{session_path}'. Ensure authentication in web UI."
            print(f"ERROR: {error_msg}")
            log_to_firestore(db, app_id, error_msg, type='error', details={'path': session_path})
            return None

        config_data = config_doc.to_dict()
        session_data = session_doc.to_dict()

        api_key = config_data.get('apiKey')
        api_secret = config_data.get('apiSecret')
        session_key = session_data.get('sessionKey') # Changed from 'key' to 'sessionKey' based on common practice
        username = session_data.get('name') # 'name' is typical for username in Last.fm session response

        if not all([api_key, api_secret, session_key, username]):
            missing_fields = []
            if not api_key: missing_fields.append("'apiKey' from config")
            if not api_secret: missing_fields.append("'apiSecret' from config")
            if not session_key: missing_fields.append("'sessionKey' from session")
            if not username: missing_fields.append("'name' (username) from session")
            error_msg = f"Last.fm configuration is incomplete. Missing: {', '.join(missing_fields)}."
            print(f"ERROR: {error_msg}")
            log_to_firestore(db, app_id, error_msg, type='error', details={'missing': missing_fields})
            return None

        success_msg = f"Successfully loaded Last.fm config for user '{username}'."
        print(success_msg)
        log_to_firestore(db, app_id, success_msg, type='success', details={'user': username})
        return {
            'api_key': api_key,
            'api_secret': api_secret,
            'session_key': session_key,
            'username': username
        }

    except Exception as e:
        error_msg = f"Failed to retrieve Last.fm configuration from Firestore: {e}"
        print(f"ERROR: {error_msg}")
        log_to_firestore(db, app_id, error_msg, type='error', details={'exception': str(e)})
        return None

def get_album_details_from_firestore(db, app_id, rfid_tag):
    """
    Fetches album details (artist, album) from Firestore based on RFID tag.
    """
    album_path = f'artifacts/{app_id}/public/data/albums/{rfid_tag}'
    log_message_start = f"Attempting to fetch album details for RFID tag '{rfid_tag}' from '{album_path}'..."
    print(log_message_start)
    # log_to_firestore(db, app_id, log_message_start, type='info', details={'rfid_tag': rfid_tag, 'path': album_path}) # Similar to above, log outcomes.
    try:
        album_doc_ref = db.document(album_path)
        album_doc = album_doc_ref.get()

        if album_doc.exists:
            album_data = album_doc.to_dict()
            if 'artist' in album_data and 'album' in album_data:
                success_msg = f"Found album details: {album_data['album']} by {album_data['artist']} for tag '{rfid_tag}'."
                print(success_msg)
                log_to_firestore(db, app_id, success_msg, type='info', details={'rfid_tag': rfid_tag, 'artist': album_data['artist'], 'album': album_data['album']})
                return album_data
            else:
                warn_msg = f"Document for RFID tag '{rfid_tag}' found, but missing 'artist' or 'album' field."
                print(f"WARN: {warn_msg}")
                log_to_firestore(db, app_id, warn_msg, type='warning', details={'rfid_tag': rfid_tag, 'data': album_data})
                return None
        else:
            warn_msg = f"No album details found in Firestore for RFID tag '{rfid_tag}'."
            print(f"WARN: {warn_msg}")
            log_to_firestore(db, app_id, warn_msg, type='warning', details={'rfid_tag': rfid_tag, 'path': album_path})
            return None
    except Exception as e:
        error_msg = f"Failed to retrieve album details from Firestore for tag '{rfid_tag}': {e}"
        print(f"ERROR: {error_msg}")
        log_to_firestore(db, app_id, error_msg, type='error', details={'rfid_tag': rfid_tag, 'exception': str(e)})
        return None

def scrobble_album(lastfm_config, artist, album):
    """
    Scrobbles an entire album to Last.fm.
    Fetches tracklist, prepares scrobble data, and sends it.
    """
    # Note: db and APP_ID are not directly available in this function's scope.
    # If we want to log from here, we'd need to pass them or use a global/class logger.
    # For now, primary logging for this function's call/outcome will be in listen_for_rfid_scans.
    # However, errors *within* this function related to API calls can still be printed.
    # We can add more granular logging here if db/APP_ID are passed in.

    if not lastfm_config or not all(k in lastfm_config for k in ['api_key', 'api_secret', 'session_key', 'username']):
        # This error is critical for the calling function to log.
        print("CRITICAL_ERROR: scrobble_album - Last.fm configuration is missing or incomplete.")
        return False # Rely on calling function to log this with context

    print(f"Attempting to scrobble album: {album} by {artist} for user {lastfm_config['username']}") # Keep for console

    # 1. Fetch Tracklist from Last.fm
    print(f"Fetching tracklist for {album} by {artist}...") # Keep for console
    album_info_params = {
        'method': 'album.getinfo',
        'artist': artist,
        'album': album,
        'username': lastfm_config['username'] # Recommended by Last.fm for personalized results
    }
    # album.getinfo does not require a signed call or session key for basic info
    album_info_response = make_lastfm_api_request(
        album_info_params,
        lastfm_config['api_key']
        # No api_secret or session_key needed for album.getinfo
    )

    if not album_info_response or 'album' not in album_info_response or 'tracks' not in album_info_response['album']:
        # This error is critical for the calling function to log.
        print(f"ERROR_API: Could not fetch tracklist for {album} by {artist}. Response: {album_info_response}")
        # Ideally, log to Firestore from here if db/app_id were available
        return False # Rely on calling function to log this failure

    tracks_data = album_info_response['album']['tracks'].get('track', [])
    if not isinstance(tracks_data, list): # If there's only one track, it might not be a list
        tracks_data = [tracks_data]

    if not tracks_data:
        print(f"WARN_API: No tracks found for {album} by {artist} in Last.fm database.")
        # Rely on calling function to log this outcome if desired.
        return False # Or handle as partial success if other logic allows

    valid_tracks = [t for t in tracks_data if t.get('name') and t.get('duration')]
    if len(valid_tracks) != len(tracks_data):
        print(f"WARN_DATA: Some tracks for {album} by {artist} were missing name or duration. Original: {len(tracks_data)}, Valid: {len(valid_tracks)}")
        # This is an internal detail, could be logged by calling function if it gets this info.

    if not valid_tracks:
        print(f"ERROR_DATA: No valid tracks (with name/duration) found for {album} by {artist} after filtering.")
        return False # Rely on calling function to log

    print(f"Found {len(valid_tracks)} tracks for {album} by {artist}.") # Keep for console

    # 2. Prepare and Send Scrobbles
    # Last.fm allows batch scrobbling of up to 50 tracks.
    # Timestamps should be in the past. We'll simulate listening from the first track to the last.
    # The timestamp is when the track *started* playing.
    current_time_unix = int(time.time())
    scrobble_params = {'method': 'track.scrobble'}

    # Sort tracks by @attr.rank to ensure they are in order, though API response usually is.
    # If rank is not available, we just use the order received.
    # Last.fm ranks are 1-based strings, so convert to int for sorting.
    try:
        valid_tracks.sort(key=lambda t: int(t.get('@attr', {}).get('rank', 0)))
    except ValueError:
        print("WARN: Could not sort tracks by rank, using received order.")

    # Calculate timestamps. The *last* track in the album list should have the most recent timestamp.
    # We work backwards from current_time_unix, subtracting duration for each prior track.
    temp_timestamp = current_time_unix
    track_timestamps = []

    for track in reversed(valid_tracks): # Iterate from last track to first
        try:
            duration = int(track.get('duration', 180)) # Default to 3 mins if somehow missing after filter
        except ValueError:
            duration = 180 # Default if duration is not a valid integer
        temp_timestamp -= duration # Timestamp for this track is before the next one played
        track_timestamps.insert(0, temp_timestamp) # Insert at beginning to re-establish correct order

    # Check if any timestamps are too old (older than 14 days) or in the future.
    # Last.fm might reject scrobbles older than 14 days.
    # Future timestamps are also invalid.
    fourteen_days_ago = current_time_unix - (14 * 24 * 60 * 60)
    final_tracks_to_scrobble = []

    for i, track in enumerate(valid_tracks):
        if track_timestamps[i] > current_time_unix + (10*60): # 10 mins in future tolerance
            print(f"WARN: Timestamp for track '{track['name']}' is in the future. Skipping this track.")
            continue
        if track_timestamps[i] < fourteen_days_ago:
            print(f"WARN: Timestamp for track '{track['name']}' is older than 14 days. Skipping this track.")
            continue
        final_tracks_to_scrobble.append((track, track_timestamps[i]))

    if not final_tracks_to_scrobble:
        print(f"ERROR_DATA: No tracks left for {album} by {artist} to scrobble after timestamp validation.")
        return False # Rely on calling function to log

    if len(final_tracks_to_scrobble) > 50:
        print(f"WARN_DATA: Album {album} by {artist} has {len(final_tracks_to_scrobble)} tracks, scrobbling the first 50.")
        final_tracks_to_scrobble = final_tracks_to_scrobble[:50]

    for i, (track, ts) in enumerate(final_tracks_to_scrobble):
        scrobble_params[f'artist[{i}]'] = artist
        scrobble_params[f'album[{i}]'] = album
        scrobble_params[f'track[{i}]'] = track['name']
        scrobble_params[f'timestamp[{i}]'] = ts

    print(f"Submitting {len(final_tracks_to_scrobble)} tracks for {album} by {artist} for scrobbling...") # Keep for console

    scrobble_response = make_lastfm_api_request(
        scrobble_params,
        api_key=lastfm_config['api_key'],
        api_secret=lastfm_config['api_secret'],
        session_key=lastfm_config['session_key'],
        http_method='POST'
    )

    if scrobble_response and 'scrobbles' in scrobble_response:
        accepted_count = int(scrobble_response['scrobbles']['@attr'].get('accepted', 0))
        ignored_count = int(scrobble_response['scrobbles']['@attr'].get('ignored', 0))
        if accepted_count > 0:
            print(f"API_SUCCESS: Successfully scrobbled {accepted_count} tracks for {album} by {artist}. Ignored: {ignored_count}.")
            # Rely on calling function to log this success, passing accepted_count.
            return {'accepted': accepted_count, 'ignored': ignored_count, 'album_scrobbled': album, 'artist_scrobbled': artist} # Return dict for richer logging
        else:
            print(f"WARN_API: Last.fm accepted 0 tracks for {album} by {artist}. Ignored: {ignored_count}. Full response: {scrobble_response}")
            # Rely on calling function to log this, passing ignored_count and response.
            return {'accepted': 0, 'ignored': ignored_count, 'album_scrobbled': album, 'artist_scrobbled': artist, 'response': scrobble_response}
    else:
        print(f"ERROR_API: Failed to scrobble tracks for {album} by {artist}. Response: {scrobble_response}")
        # Rely on calling function to log, passing the response.
        return {'accepted': 0, 'ignored': 0, 'album_scrobbled': album, 'artist_scrobbled': artist, 'error_response': scrobble_response}

import firebase_admin
from firebase_admin import credentials, firestore

# --- CONFIGURATION ---

# 1. Firebase Service Account
#    - Go to your Firebase Project Settings -> Service accounts.
#    - Click "Generate new private key" and download the JSON file.
#    - Place the file in the same directory as this script.
#    - RENAME THE FILE to 'serviceAccountKey.json' or update the path below.
try:
    cred = credentials.Certificate('serviceAccountKey.json')
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("Successfully connected to Firebase.")
except Exception as e:
    print(f"ERROR: Could not initialize Firebase. Make sure 'serviceAccountKey.json' is correct. {e}")
    exit()


# 2. Your App ID
#    - This MUST match the App ID from the web app environment.
#    - You can find it on the web app's footer.
APP_ID = 'default-scrobbler-app' # <--- IMPORTANT: REPLACE WITH YOUR REAL APP ID

# 3. Target User ID for Last.fm Scrobbling
#    - This is the user whose Last.fm account will be used for scrobbling.
#    - You can find this ID in the footer of the WebUI after logging in.
TARGET_USER_ID = 'YOUR_USER_ID_FROM_WEB_UI' # <--- IMPORTANT: REPLACE WITH THE ACTUAL USER ID

# 4. Serial Port for RFID Reader
#    - Your RFID reader should appear as a serial device.
#    - On Linux/macOS, it's often '/dev/ttyUSB0' or '/dev/tty.usbmodem...'.
#    - On Windows, it's 'COM3', 'COM4', etc.
#    - Check your system's device manager to find the correct port.
SERIAL_PORT = '/dev/ttyUSB0'  # <-- CHANGE THIS TO YOUR READER'S PORT
BAUD_RATE = 9600


# --- MAIN SCRIPT LOGIC ---

def listen_for_rfid_scans():
    """
    Opens the serial port and continuously listens for RFID tag IDs.
    When a tag is read, it writes it to the Firestore 'scans' collection.
    """
    # --- Try to load Last.fm configuration ---
    if not db: # db might not be initialized if Firebase connection failed.
        err_msg = "Firestore client not available. Cannot fetch Last.fm config. Exiting script."
        print(f"ERROR: {err_msg}")
        # Cannot log to Firestore if db is not available.
        return

    if APP_ID == 'default-scrobbler-app' or TARGET_USER_ID == 'YOUR_USER_ID_FROM_WEB_UI':
        err_msg = "APP_ID or TARGET_USER_ID is not configured. Please update these variables in the script. Exiting."
        print(f"ERROR: {err_msg}")
        log_to_firestore(db, APP_ID, err_msg, type='error', details={'app_id': APP_ID, 'target_user_id': TARGET_USER_ID})
        return

    lastfm_config = get_lastfm_config_from_firestore(db, APP_ID, TARGET_USER_ID)

    if not lastfm_config:
        err_msg = "Failed to load Last.fm configuration from Firestore. Scrobbling will not be possible."
        print(f"ERROR: {err_msg}")
        log_to_firestore(db, APP_ID, err_msg, type='error')
        # Script continues without Last.fm features as per previous logic.
        # log_to_firestore(db, APP_ID, "Continuing without Last.fm functionality.", type='warning') # Already logged by get_lastfm_config
    else:
        # Success message already logged by get_lastfm_config_from_firestore
        pass

    # --- Main RFID listening loop ---
    while True:
        try:
            log_to_firestore(db, APP_ID, f"Attempting to connect to RFID reader on {SERIAL_PORT}...", type='info', details={'serial_port': SERIAL_PORT})
            print(f"Attempting to connect to RFID reader on {SERIAL_PORT}...")
            with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1) as ser:
                connect_msg = f"Successfully connected to RFID reader on {SERIAL_PORT}. Waiting for scans..."
                print(connect_msg)
                log_to_firestore(db, APP_ID, connect_msg, type='success', details={'serial_port': SERIAL_PORT})
                while True:
                    line = ser.readline()
                    if line:
                        tag_id = line.decode('utf-8').strip()
                        if tag_id:
                            scan_msg = f"Tag Scanned: {tag_id}"
                            print(f"--- {scan_msg} ---")
                            log_to_firestore(db, APP_ID, scan_msg, type='scan', details={'rfid_tag': tag_id})

                            if not lastfm_config or not lastfm_config.get('api_key'):
                                err_msg_scrobble = "Last.fm configuration not available or incomplete. Cannot scrobble."
                                print(err_msg_scrobble)
                                log_to_firestore(db, APP_ID, err_msg_scrobble, type='warning', details={'rfid_tag': tag_id})
                                continue

                            album_data = get_album_details_from_firestore(db, APP_ID, tag_id) # This function now logs its outcome

                            if album_data:
                                artist = album_data.get('artist')
                                album = album_data.get('album')
                                if artist and album:
                                    scrobble_attempt_msg = f"Attempting to scrobble album: '{album}' by '{artist}' for tag '{tag_id}'."
                                    print(scrobble_attempt_msg)
                                    log_to_firestore(db, APP_ID, scrobble_attempt_msg, type='info', details={'rfid_tag': tag_id, 'artist': artist, 'album': album})

                                    scrobble_result = scrobble_album(lastfm_config, artist, album)

                                    if isinstance(scrobble_result, dict) and scrobble_result.get('accepted', 0) > 0:
                                        scrobble_success_msg = f"Successfully scrobbled {scrobble_result['accepted']} tracks for album '{album}' by '{artist}' (Tag: {tag_id}). Ignored: {scrobble_result.get('ignored',0)}."
                                        print(scrobble_success_msg)
                                        log_to_firestore(db, APP_ID, scrobble_success_msg, type='success',
                                                         details={'rfid_tag': tag_id, 'artist': artist, 'album': album, 'accepted_tracks': scrobble_result['accepted'], 'ignored_tracks': scrobble_result.get('ignored',0)})
                                    elif isinstance(scrobble_result, dict): # Handle cases where accepted might be 0 or error occurred
                                        err_detail = scrobble_result.get('error_response') or scrobble_result.get('response') or "No specific error from Last.fm but scrobble not accepted."
                                        scrobble_fail_msg = f"Failed to scrobble album '{album}' by '{artist}' (Tag: {tag_id}). Accepted: {scrobble_result.get('accepted',0)}, Ignored: {scrobble_result.get('ignored',0)}."
                                        print(scrobble_fail_msg)
                                        log_to_firestore(db, APP_ID, scrobble_fail_msg, type='error',
                                                         details={'rfid_tag': tag_id, 'artist': artist, 'album': album, 'lastfm_response': str(err_detail)})
                                    else: # Fallback for unexpected scrobble_album responses (e.g. False from config error)
                                        scrobble_generic_fail_msg = f"Scrobbling failed for album '{album}' by '{artist}' (Tag: {tag_id}). See console for internal errors."
                                        print(scrobble_generic_fail_msg)
                                        log_to_firestore(db, APP_ID, scrobble_generic_fail_msg, type='error',
                                                         details={'rfid_tag': tag_id, 'artist': artist, 'album': album, 'raw_scrobble_response': str(scrobble_result)})

                                else:
                                    # This case is already logged by get_album_details_from_firestore if fields are missing
                                    pass
                            else:
                                # This case is already logged by get_album_details_from_firestore if tag not found
                                pass

        except serial.SerialException as e:
            err_msg = f"Serial port error: {e}. Please check port '{SERIAL_PORT}' and reader connection. Retrying in 10s."
            print(f"Error: {err_msg}")
            log_to_firestore(db, APP_ID, err_msg, type='error', details={'serial_port': SERIAL_PORT, 'exception': str(e)})
            time.sleep(10)
        except Exception as e:
            err_msg = f"An unexpected error occurred in RFID listening loop: {e}. Retrying in 10s."
            print(f"Error: {err_msg}")
            log_to_firestore(db, APP_ID, err_msg, type='error', details={'exception': str(e)})
            time.sleep(10)


if __name__ == '__main__':
    # Initial check for APP_ID to allow some startup logging if it's default.
    # The main function `listen_for_rfid_scans` will do a more restrictive check.
    if db and APP_ID and APP_ID != 'default-scrobbler-app':
        log_to_firestore(db, APP_ID, "RFID Scrobbler script started.", type='info')
    elif db and APP_ID == 'default-scrobbler-app':
         print("WARNING: You are using the default App ID. Script logs to Firestore will use this default ID.")
         log_to_firestore(db, APP_ID, "RFID Scrobbler script started with DEFAULT App ID.", type='warning')
    else: # db might not be available yet
        print("RFID Scrobbler script starting...")


    if APP_ID == 'default-scrobbler-app': # Redundant console print, but good for immediate visibility
         print("WARNING: You are using the default App ID. Please update the APP_ID variable in the script for correct operation with the Web UI.")

    listen_for_rfid_scans()

