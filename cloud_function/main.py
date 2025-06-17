import base64
import json
import os
import hashlib
import time
import requests # For Last.fm API calls

# Firebase Admin SDK
import firebase_admin
from firebase_admin import credentials, firestore

# --- Global Variables & Initialization ---
LASTFM_API_URL = "https://ws.audioscrobbler.com/2.0/"
APP_ID = ""
TARGET_USER_ID = ""
db = None

# Attempt to initialize Firebase Admin SDK only once.
if not firebase_admin._apps:
    try:
        APP_ID = os.environ.get("APP_ID")
        TARGET_USER_ID = os.environ.get("TARGET_USER_ID")

        if not APP_ID or not TARGET_USER_ID:
            print("ERROR: APP_ID or TARGET_USER_ID environment variables not set.")
            # This is a critical configuration error.

        cred = credentials.ApplicationDefault()
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        print(f"Firebase Admin SDK initialized. APP_ID: {APP_ID}, TARGET_USER_ID: {TARGET_USER_ID}")
    except Exception as e:
        print(f"CRITICAL ERROR: Could not initialize Firebase Admin SDK: {e}")
        # db will remain None

# --- Logging Helper ---
def log_to_firestore(fs_db, app_id_val, message, type='info', details=None, rfid_tag=None):
    if not fs_db or not app_id_val:
        print(f"Log suppressed (db or app_id missing): {message}")
        return
    try:
        log_entry_path_base = f'artifacts/{app_id_val}/public/data/script_logs'
        log_entry = {
            'timestamp': firestore.SERVER_TIMESTAMP,
            'message': message,
            'type': type,
            'source': 'cloud_function'
        }
        if details: log_entry['details'] = details
        if rfid_tag: log_entry['rfid_tag'] = rfid_tag
        fs_db.collection(log_entry_path_base).add(log_entry)
    except Exception as e:
        print(f"ERROR: Firestore logging failed: {e} (Original: {message})")

# --- Last.fm API Helpers ---
def generate_api_signature(params, secret):
    sorted_params = sorted(params.items())
    signature_string = "".join([f"{k}{v}" for k, v in sorted_params])
    signature_string += secret
    return hashlib.md5(signature_string.encode('utf-8')).hexdigest()

def make_lastfm_api_request(params, api_key, api_secret=None, session_key=None, http_method='GET', current_rfid_tag=None):
    params['api_key'] = api_key
    if session_key: params['sk'] = session_key
    if api_secret:
        params['api_sig'] = generate_api_signature({k: v for k, v in params.items() if k != 'format'}, api_secret)
    params['format'] = 'json'

    try:
        if http_method.upper() == 'POST':
            response = requests.post(LASTFM_API_URL, data=params)
        else:
            response = requests.get(LASTFM_API_URL, params=params)
        response.raise_for_status()
        parsed_response = response.json() # Assume Last.fm always returns JSON or error handled by raise_for_status
        if 'error' in parsed_response:
            err_msg = f"Last.fm API Error: {parsed_response.get('message', 'Unknown')} (Code: {parsed_response.get('error', 'N/A')})"
            log_to_firestore(db, APP_ID, err_msg, type='error', details={'params': params, 'response': parsed_response}, rfid_tag=current_rfid_tag)
            return None
        return parsed_response
    except requests.exceptions.HTTPError as e:
        err_msg = f"Last.fm HTTP Error: {e.response.status_code}. Response: {e.response.text[:200]}"
        log_to_firestore(db, APP_ID, err_msg, type='error', details={'params': params, 'exception': str(e)}, rfid_tag=current_rfid_tag)
        return None
    except Exception as e: # Catch other errors like JSONDecodeError or broader RequestException
        err_msg = f"Last.fm API request unexpected error: {e}"
        log_to_firestore(db, APP_ID, err_msg, type='error', details={'params': params, 'exception': str(e)}, rfid_tag=current_rfid_tag)
        return None

# --- Firestore Data Fetchers ---
def get_lastfm_config_from_firestore(fs_db, app_id_val, user_id_val, current_rfid_tag=None):
    if not fs_db or not app_id_val or not user_id_val: return None
    config_path = f'artifacts/{app_id_val}/users/{user_id_val}/config/lastfm'
    session_path = f'artifacts/{app_id_val}/users/{user_id_val}/config/lastfm_session'
    try:
        config_doc = fs_db.document(config_path).get()
        session_doc = fs_db.document(session_path).get()
        if not config_doc.exists or not session_doc.exists:
            log_to_firestore(fs_db, app_id_val, "Last.fm config/session not found.", type='error', rfid_tag=current_rfid_tag)
            return None
        config_data, session_data = config_doc.to_dict(), session_doc.to_dict()
        api_key = config_data.get('apiKey')
        api_secret = config_data.get('apiSecret')
        session_key = session_data.get('sessionKey')
        username = session_data.get('name')
        if not all([api_key, api_secret, session_key, username]):
            log_to_firestore(fs_db, app_id_val, "Last.fm config incomplete.", type='error', rfid_tag=current_rfid_tag)
            return None
        return {'api_key': api_key, 'api_secret': api_secret, 'session_key': session_key, 'username': username}
    except Exception as e:
        log_to_firestore(fs_db, app_id_val, f"Failed to get Last.fm config: {e}", type='error', rfid_tag=current_rfid_tag)
        return None

def get_album_details_from_firestore(fs_db, app_id_val, rfid_tag_val):
    if not fs_db or not app_id_val or not rfid_tag_val: return None
    album_path = f'artifacts/{app_id_val}/public/data/albums/{rfid_tag_val}'
    try:
        album_doc = fs_db.document(album_path).get()
        if album_doc.exists:
            album_data = album_doc.to_dict()
            if 'artist' in album_data and 'album' in album_data:
                return album_data
            log_to_firestore(fs_db, app_id_val, "Album data missing artist/album.", type='warning', rfid_tag=rfid_tag_val)
            return None
        log_to_firestore(fs_db, app_id_val, "No album details for RFID tag.", type='info', rfid_tag=rfid_tag_val)
        return None
    except Exception as e:
        log_to_firestore(fs_db, app_id_val, f"Failed to get album details: {e}", type='error', rfid_tag=rfid_tag_val)
        return None

# --- Scrobbling Logic ---
def scrobble_album(lastfm_cfg, artist, album_name, fs_db, app_id_val, current_rfid_tag=None):
    log_to_firestore(fs_db, app_id_val, f"Scrobbling: {album_name} by {artist}", type='info', rfid_tag=current_rfid_tag)
    album_info_params = {'method': 'album.getinfo', 'artist': artist, 'album': album_name, 'username': lastfm_cfg['username']}
    album_info = make_lastfm_api_request(album_info_params, lastfm_cfg['api_key'], current_rfid_tag=current_rfid_tag)

    if not album_info or 'album' not in album_info or 'tracks' not in album_info['album']:
        log_to_firestore(fs_db, app_id_val, f"Could not fetch tracklist for {album_name}.", type='error', rfid_tag=current_rfid_tag)
        return {'accepted': 0, 'error': 'Failed to fetch tracklist'}

    tracks_data = album_info['album']['tracks'].get('track', [])
    if not isinstance(tracks_data, list): tracks_data = [tracks_data]
    valid_tracks = [t for t in tracks_data if t.get('name') and t.get('duration')]
    if not valid_tracks:
        log_to_firestore(fs_db, app_id_val, f"No valid tracks for {album_name}.", type='warning', rfid_tag=current_rfid_tag)
        return {'accepted': 0, 'error': 'No valid tracks'}

    current_time_unix = int(time.time())
    track_timestamps = []
    temp_timestamp = current_time_unix
    try: # Sort by rank if available
        valid_tracks.sort(key=lambda t: int(t.get('@attr', {}).get('rank', 0)))
    except ValueError: pass # Ignore if rank is not sortable

    for track in reversed(valid_tracks):
        duration = int(track.get('duration', 180))
        temp_timestamp -= duration
        track_timestamps.insert(0, temp_timestamp)

    fourteen_days_ago = current_time_unix - (14 * 24 * 60 * 60)
    final_tracks = [(t, ts) for t, ts in zip(valid_tracks, track_timestamps) if fourteen_days_ago < ts < current_time_unix + (10*60)]

    if not final_tracks:
        log_to_firestore(fs_db, app_id_val, f"No tracks for {album_name} after timestamp validation.", type='info', rfid_tag=current_rfid_tag)
        return {'accepted': 0, 'error': 'No tracks after timestamp validation'}

    final_tracks = final_tracks[:50] # Max 50 tracks per batch
    scrobble_params = {'method': 'track.scrobble'}
    for i, (track, ts) in enumerate(final_tracks):
        scrobble_params[f'artist[{i}]'] = artist
        scrobble_params[f'album[{i}]'] = album_name
        scrobble_params[f'track[{i}]'] = track['name']
        scrobble_params[f'timestamp[{i}]'] = ts

    response = make_lastfm_api_request(scrobble_params, lastfm_cfg['api_key'], lastfm_cfg['api_secret'], lastfm_cfg['session_key'], 'POST', current_rfid_tag)
    if response and 'scrobbles' in response:
        accepted = int(response['scrobbles']['@attr'].get('accepted', 0))
        ignored = int(response['scrobbles']['@attr'].get('ignored', 0))
        log_to_firestore(fs_db, app_id_val, f"Scrobbled {album_name}: {accepted} accepted, {ignored} ignored.", type='success' if accepted > 0 else 'warning', rfid_tag=current_rfid_tag)
        return {'accepted': accepted, 'ignored': ignored}
    log_to_firestore(fs_db, app_id_val, f"Failed to scrobble {album_name}.", type='error', details=response, rfid_tag=current_rfid_tag)
    return {'accepted': 0, 'error': 'Scrobble API call failed', 'response': response}

# --- Cloud Function Entry Point ---
def rfid_scrobbler_function(event, context):
    if not db or not APP_ID or not TARGET_USER_ID:
        print("FATAL: Cloud Function not configured (db, APP_ID, or TARGET_USER_ID missing).")
        return 'Function configuration error', 500

    pubsub_data = event.get('data')
    if not pubsub_data:
        log_to_firestore(db, APP_ID, "No data in Pub/Sub message.", type='error')
        return 'No Pub/Sub data', 400

    try:
        rfid_tag = base64.b64decode(pubsub_data).decode('utf-8').strip()
        if not rfid_tag:
            log_to_firestore(db, APP_ID, "Empty RFID tag after decoding.", type='warning')
            return 'Empty RFID tag', 400
        log_to_firestore(db, APP_ID, f"Processing RFID: {rfid_tag}", type='info', rfid_tag=rfid_tag)
    except Exception as e:
        log_to_firestore(db, APP_ID, "Error decoding Pub/Sub message.", type='error', details=str(e))
        return 'Decode error', 400

    lastfm_config = get_lastfm_config_from_firestore(db, APP_ID, TARGET_USER_ID, rfid_tag)
    if not lastfm_config:
        return f'Last.fm config error for {TARGET_USER_ID}. Cannot process {rfid_tag}.', 200 # 200 as tag processed, but no action

    album_data = get_album_details_from_firestore(db, APP_ID, rfid_tag)
    if not album_data:
        return f'No album details for RFID {rfid_tag}.', 200 # Expected

    artist = album_data.get('artist')
    album = album_data.get('album')
    if not artist or not album:
        log_to_firestore(db, APP_ID, f"Artist/Album missing for tag {rfid_tag}.", type='warning', rfid_tag=rfid_tag)
        return f'Artist/Album missing for {rfid_tag}.', 200 # Expected

    result = scrobble_album(lastfm_config, artist, album, db, APP_ID, rfid_tag)
    if result.get('accepted', 0) > 0:
        return f"Scrobbled '{album}': {result['accepted']} tracks.", 200
    return f"Scrobbling failed for '{album}'. Error: {result.get('error', 'Unknown')}", 200
