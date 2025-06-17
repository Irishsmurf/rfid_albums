# import serial
import board
import busio
import time
# import requests
# The adafruit_requests library and its dependencies (like adafruit_bus_device,
# adafruit_minimqtt if HTTPS is used with certain WiFi modules) must be
# installed in the CircuitPython device's `lib` folder.
import adafruit_requests as requests
# hashlib.md5 is generally available in CircuitPython.
import hashlib
import json
import config # Added for local configuration
import wifi
import socketpool
import ssl

# Firebase Admin SDK imports removed
# import firebase_admin
# from firebase_admin import credentials, firestore

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

def make_lastfm_api_request(requests_session, params, api_key, api_secret=None, session_key=None, http_method='GET'):
    """
    Makes a request to the Last.fm API using the provided adafruit_requests session.
    Handles API key, session key, signature generation, and HTTP method.
    Returns parsed JSON response or None on error.
    """
    if not requests_session:
        print("ERROR: No requests session available. Cannot make Last.fm API request.")
        return None

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
            response = requests_session.post(LASTFM_API_URL, data=params)
        else:
            response = requests_session.get(LASTFM_API_URL, params=params)

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

    # adafruit_requests typically raises RuntimeError for network/socket issues.
    # It might have specific exceptions like HTTPError, but this needs to be confirmed.
    # For now, we'll catch RuntimeError for general network problems and a generic Exception.
    except RuntimeError as e: # More common for adafruit_requests connection errors
        print(f"Network/Runtime Error during API request: {e}")
        return None
    except requests.HTTPError as e: # Assuming adafruit_requests.HTTPError exists
        print(f"HTTP Error: {e.response.status_code} - {e.response.reason}")
        print(f"Response content: {e.response.text[:200]}...")
        return None
    except json.JSONDecodeError as e:
        print(f"Failed to parse JSON response: {e}")
        # response might not be defined if error occurred before request completed.
        # print(f"Response content: {response.text[:200]}...")
        return None
    except Exception as e: # Catch any other unexpected errors
        print(f"An unexpected error occurred during API request: {e}")
        return None

# Firestore-dependent functions log_to_firestore, get_lastfm_config_from_firestore,
# and get_album_details_from_firestore were confirmed removed in a previous step or will be by this diff.

def scrobble_album(requests_session, lastfm_config, artist, album):
    """
    Scrobbles an entire album to Last.fm using the provided requests_session.
    Fetches tracklist, prepares scrobble data, and sends it.
    """
    if not requests_session:
        print("ERROR: scrobble_album - No requests session available. Cannot scrobble.")
        return False

    if not lastfm_config or not all(k in lastfm_config for k in ['api_key', 'api_secret', 'session_key', 'username']):
        print("CRITICAL_ERROR: scrobble_album - Last.fm configuration is missing or incomplete.")
        return False

    print(f"Attempting to scrobble album: {album} by {artist} for user {lastfm_config['username']}")

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
        requests_session,
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

    print(f"Submitting {len(final_tracks_to_scrobble)} tracks for {album} by {artist} for scrobbling...")

    scrobble_response = make_lastfm_api_request(
        requests_session,
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

# Firebase Admin SDK imports and initialization code removed.
# Global constants for APP_ID, TARGET_USER_ID, SERIAL_PORT, BAUD_RATE removed.
# These will be accessed via the 'config' module.

# --- MAIN SCRIPT LOGIC ---

def listen_for_rfid_scans(requests_session):
    """
    Opens the serial port and continuously listens for RFID tag IDs.
    When a tag is read, it attempts to scrobble it based on local config
    using the provided requests_session.
    """
    # --- Load Last.fm configuration from config.py ---
    lastfm_config = None
    if hasattr(config, 'LASTFM_API_KEY') and \
       hasattr(config, 'LASTFM_API_SECRET') and \
       hasattr(config, 'LASTFM_SESSION_KEY') and \
       hasattr(config, 'LASTFM_USERNAME'):
        lastfm_config = {
            'api_key': config.LASTFM_API_KEY,
            'api_secret': config.LASTFM_API_SECRET,
            'session_key': config.LASTFM_SESSION_KEY,
            'username': config.LASTFM_USERNAME
        }
        print("INFO: Successfully loaded Last.fm configuration from config.py")
    else:
        print("ERROR: Last.fm configuration is incomplete in config.py. Missing API key, secret, session key, or username. Scrobbling will not be possible.")
        # Script will continue, but scrobbling attempts will fail cleanly.

    # Check for default APP_ID and TARGET_USER_ID from config module
    # These might be used for logging or other non-critical functions if adapted later.
    # For now, their primary check is at startup.
    current_app_id = getattr(config, 'APP_ID', 'config_app_id_missing')
    current_target_user_id = getattr(config, 'TARGET_USER_ID', 'config_target_user_id_missing')

    if current_app_id == 'my-rfid-scrobbler' or current_target_user_id == 'my-user-id':
        print(f"WARN: APP_ID ('{current_app_id}') or TARGET_USER_ID ('{current_target_user_id}') might be using default values from config_example.py. Update if necessary.")

    # --- Main RFID listening loop ---
    uart = None # Initialize uart to None; it will be set up inside the loop.
    while True:
        try:
            # --- UART/Serial Port Setup Phase (if needed) ---
            if uart is None: # Only attempt to initialize if not already set up or after an error
                if config.SERIAL_PORT == "SIMULATE":
                    print("INFO: RFID Reader in SIMULATION MODE. Type tag ID and press Enter.")
                    # uart remains None, readline will be simulated later in the loop
                elif isinstance(config.SERIAL_PORT, tuple) and len(config.SERIAL_PORT) == 2:
                    tx_pin, rx_pin = config.SERIAL_PORT
                    # The pins in config.SERIAL_PORT must be actual board.Pin objects for busio.UART
                    # e.g., config.SERIAL_PORT = (board.IO12, board.IO13)
                    print(f"INFO: Attempting to initialize UART: TX={tx_pin}, RX={rx_pin} at {config.BAUD_RATE} baud")
                    try:
                        uart = busio.UART(tx_pin, rx_pin, baudrate=config.BAUD_RATE, timeout=1)
                        print(f"INFO: Successfully initialized UART on TX={tx_pin}, RX={rx_pin}.")
                    except RuntimeError as e:
                        print(f"ERROR: Failed to initialize UART on pins TX={tx_pin}, RX={rx_pin}: {e}")
                        raise # Reraise to be caught by the outer loop's error handling
                    except TypeError as e: # busio.UART might raise TypeError if pins are not Pin objects
                        print(f"ERROR: Invalid pin types for UART (TX={tx_pin}, RX={rx_pin}). Ensure they are board.Pin objects in config.py. Error: {e}")
                        raise ValueError("Invalid SERIAL_PORT pin types in configuration.") # Reraise as ValueError
                else:
                    print(f"ERROR: config.SERIAL_PORT is not 'SIMULATE' or a valid (board.TX_PIN, board.RX_PIN) tuple. Value: {config.SERIAL_PORT}")
                    raise ValueError("Invalid SERIAL_PORT configuration.") # To trigger the sleep/retry in outer loop

            # --- RFID Tag Reading Phase ---
            line = None
            if config.SERIAL_PORT == "SIMULATE":
                # Simulation mode: read from console input
                print("SIMULATING RFID SCAN (Type a tag ID and press Enter, or Ctrl+D/Ctrl+C to exit simulation):")
                try:
                    sim_input = input()
                    if not sim_input: # User pressed enter without typing
                        time.sleep(config.NO_DATA_SLEEP_INTERVAL if hasattr(config, 'NO_DATA_SLEEP_INTERVAL') else 0.1)
                        continue # Go to next iteration of inner while loop
                    line = sim_input.encode('utf-8') # Add newline if your processing expects it, not needed for .strip()
                except EOFError:
                    print("INFO: EOF received in simulation mode. Exiting script.")
                    return # Exit listen_for_rfid_scans, and thus the script
                except KeyboardInterrupt:
                    print("INFO: Keyboard interrupt in simulation. Exiting script.")
                    return # Exit listen_for_rfid_scans
            elif uart:
                # Hardware UART mode
                line = uart.readline()
                if line is None: # readline() timed out
                    time.sleep(config.NO_DATA_SLEEP_INTERVAL if hasattr(config, 'NO_DATA_SLEEP_INTERVAL') else 0.1)
                    continue # Go to next iteration of inner while loop
            else:
                # Should not happen if SERIAL_PORT config is valid and not SIMULATE,
                # as uart should be initialized or an error raised.
                # This means UART setup failed in a way not caught above, or SERIAL_PORT is invalid.
                # This will lead to the main error handlers and retry.
                print("ERROR: UART not available for reading and not in SIMULATE mode. Check configuration.")
                raise RuntimeError("UART became unavailable unexpectedly.")

            # --- Tag Processing Phase ---
            if line: # Only process if line is not None
                tag_id = line.decode('utf-8').strip()
                if tag_id:
                    scan_msg = f"Tag Scanned: {tag_id}"
                    print(f"--- {scan_msg} ---")

                    if not lastfm_config:
                        print("WARN: Last.fm configuration not available or incomplete. Cannot scrobble.")
                        continue

                    album_data = None
                    if hasattr(config, 'RFID_ALBUM_MAPPINGS') and isinstance(config.RFID_ALBUM_MAPPINGS, dict) and tag_id in config.RFID_ALBUM_MAPPINGS:
                        album_data = config.RFID_ALBUM_MAPPINGS[tag_id]
                        if isinstance(album_data, dict) and 'artist' in album_data and 'album' in album_data:
                            print(f"INFO: Found album details in config.py: '{album_data['album']}' by '{album_data['artist']}' for tag '{tag_id}'.")
                        else:
                            print(f"WARN: RFID tag '{tag_id}' found in RFID_ALBUM_MAPPINGS, but data is malformed (expected dict with 'artist' and 'album'). Check config.py.")
                            album_data = None
                    else:
                        print(f"WARN: No album details found in config.py for RFID tag '{tag_id}'.")

                    if album_data:
                        artist = album_data.get('artist')
                        album = album_data.get('album')
                        scrobble_attempt_msg = f"Attempting to scrobble album: '{album}' by '{artist}' for tag '{tag_id}'."
                        print(f"INFO: {scrobble_attempt_msg}")

                        if not requests_session:
                            print("WARN: No network session. Cannot scrobble.")
                        else:
                            scrobble_result = scrobble_album(requests_session, lastfm_config, artist, album)
                            if isinstance(scrobble_result, dict) and scrobble_result.get('accepted', 0) > 0:
                                scrobble_success_msg = f"Successfully scrobbled {scrobble_result['accepted']} tracks for album '{album}' by '{artist}' (Tag: {tag_id}). Ignored: {scrobble_result.get('ignored',0)}."
                                print(f"INFO: {scrobble_success_msg}")
                            elif isinstance(scrobble_result, dict):
                                err_detail = scrobble_result.get('error_response') or scrobble_result.get('response') or "No specific error from Last.fm but scrobble not accepted."
                                scrobble_fail_msg = f"Failed to scrobble album '{album}' by '{artist}' (Tag: {tag_id}). Accepted: {scrobble_result.get('accepted',0)}, Ignored: {scrobble_result.get('ignored',0)}."
                                print(f"ERROR: {scrobble_fail_msg} - Details: {str(err_detail)}")
                            else:
                                scrobble_generic_fail_msg = f"Scrobbling failed for album '{album}' by '{artist}' (Tag: {tag_id}). See console for internal errors. Scrobble_result: {str(scrobble_result)}"
                                print(f"ERROR: {scrobble_generic_fail_msg}")
            # End of "if line:" processing block. If line was None (after timeout or empty simulation input), we just loop.
            # The NO_DATA_SLEEP_INTERVAL handles the CPU usage for this case.

        except (busio.UART.error, OSError, ValueError) as e: # Catch specific serial/OS/config errors. ValueError for invalid config.
            err_msg = f"UART/Serial port or Configuration error: {e}. "
            print(f"ERROR: {err_msg}")
            if uart:
                try:
                    uart.deinit()
                except Exception as deinit_e:
                    print(f"ERROR: Exception during UART deinit after error: {deinit_e}")
            uart = None # Crucial: reset uart so it's re-initialized in the next iteration
            retry_delay = config.RETRY_DELAY_SERIAL_ERROR if hasattr(config, 'RETRY_DELAY_SERIAL_ERROR') else 10
            print(f"INFO: Retrying in {retry_delay} seconds...")
            time.sleep(retry_delay)
        except AttributeError as e:
            print(f"ERROR: Configuration attribute missing: {e}. Please ensure config.py is complete. Exiting.")
            return
        except Exception as e:
            err_msg = f"An unexpected error occurred in RFID listening loop: {e} (Type: {type(e)})."
            print(f"ERROR: {err_msg}")
            if uart:
                try:
                    uart.deinit()
                except Exception as deinit_e:
                    print(f"ERROR: Exception during UART deinit after unexpected error: {deinit_e}")
            uart = None # Crucial: reset uart
            retry_delay = config.RETRY_DELAY_UNEXPECTED_ERROR if hasattr(config, 'RETRY_DELAY_UNEXPECTED_ERROR') else 10
            print(f"INFO: Retrying in {retry_delay} seconds...")
            time.sleep(retry_delay)


if __name__ == '__main__':


                if line:
                    tag_id = line.decode('utf-8').strip()
                    if tag_id:
                        scan_msg = f"Tag Scanned: {tag_id}"
                        print(f"--- {scan_msg} ---")
                        # print(f"INFO: {scan_msg} (Tag: {tag_id})") # Redundant with above print

                        if not lastfm_config: # Check if Last.fm config was loaded successfully
                            print("WARN: Last.fm configuration not available or incomplete (checked from listen_for_rfid_scans). Cannot scrobble.")
                            continue # Process next scan without attempting scrobble

                        # Get album details from config.RFID_ALBUM_MAPPINGS
                        album_data = None
                        if hasattr(config, 'RFID_ALBUM_MAPPINGS') and isinstance(config.RFID_ALBUM_MAPPINGS, dict) and tag_id in config.RFID_ALBUM_MAPPINGS:
                            album_data = config.RFID_ALBUM_MAPPINGS[tag_id]
                            if isinstance(album_data, dict) and 'artist' in album_data and 'album' in album_data:
                                print(f"INFO: Found album details in config.py: '{album_data['album']}' by '{album_data['artist']}' for tag '{tag_id}'.")
                            else:
                                print(f"WARN: RFID tag '{tag_id}' found in RFID_ALBUM_MAPPINGS, but data is malformed (expected dict with 'artist' and 'album'). Check config.py.")
                                album_data = None # Treat as not found
                        else:
                            print(f"WARN: No album details found in config.py for RFID tag '{tag_id}'.")

                        if album_data:
                            artist = album_data.get('artist')
                            album = album_data.get('album')
                            # Already checked for artist and album presence above
                            scrobble_attempt_msg = f"Attempting to scrobble album: '{album}' by '{artist}' for tag '{tag_id}'."
                            print(f"INFO: {scrobble_attempt_msg}")

                            if not requests_session:
                                print("WARN: No network session. Cannot scrobble.")
                            else:
                                scrobble_result = scrobble_album(requests_session, lastfm_config, artist, album)

                                if isinstance(scrobble_result, dict) and scrobble_result.get('accepted', 0) > 0:
                                    scrobble_success_msg = f"Successfully scrobbled {scrobble_result['accepted']} tracks for album '{album}' by '{artist}' (Tag: {tag_id}). Ignored: {scrobble_result.get('ignored',0)}."
                                print(f"INFO: {scrobble_success_msg}")
                            elif isinstance(scrobble_result, dict):
                                err_detail = scrobble_result.get('error_response') or scrobble_result.get('response') or "No specific error from Last.fm but scrobble not accepted."
                                scrobble_fail_msg = f"Failed to scrobble album '{album}' by '{artist}' (Tag: {tag_id}). Accepted: {scrobble_result.get('accepted',0)}, Ignored: {scrobble_result.get('ignored',0)}."
                                print(f"ERROR: {scrobble_fail_msg} - Details: {str(err_detail)}")
                            else: # Fallback (e.g., False from initial lastfm_config check in scrobble_album)
                                scrobble_generic_fail_msg = f"Scrobbling failed for album '{album}' by '{artist}' (Tag: {tag_id}). See console for internal errors. Scrobble_result: {str(scrobble_result)}"
                                print(f"ERROR: {scrobble_generic_fail_msg}")
                        # else: album_data was None, warning already printed.
                elif uart and line is None: # readline() timed out and returned None
                    time.sleep(config.NO_DATA_SLEEP_INTERVAL if hasattr(config, 'NO_DATA_SLEEP_INTERVAL') else 0.1)

                # If uart exists and something went wrong with readline (e.g. it returns None indefinitely or raises error)
                # This simple check might not catch all hardware readline issues.
                # A more robust solution might involve timeout on readline if it blocks.
                # The check `elif uart and line is None:` above handles the timeout case for power saving.
                # If readline were to error out, it would likely raise an exception caught by the outer try-except blocks.


            # This part of the loop is reached if the inner `while True` reading loop breaks.
            # This can happen if simulation ends (EOFError) or if we decide to break due to UART issues.
            # If it was a simulation EOF, the function returns. Otherwise, we deinit UART and retry.
            if uart: # If uart was initialized (i.e., not in SIMULATE mode where uart is None)
                print(f"WARN: UART read loop exited. Attempting to deinit and re-initialize.")
                try:
                    uart.deinit()
                except Exception as deinit_e:
                    print(f"ERROR: Exception during UART deinit: {deinit_e}")
                uart = None # Ensure uart is None before retrying connection

            # For non-simulation mode, or if simulation loop breaks unexpectedly, retry after delay.
            # The simulation EOF case already returned.
            print(f"INFO: Retrying connection/setup in {config.RETRY_DELAY_SERIAL_ERROR if hasattr(config, 'RETRY_DELAY_SERIAL_ERROR') else 10} seconds...")
            time.sleep(config.RETRY_DELAY_SERIAL_ERROR if hasattr(config, 'RETRY_DELAY_SERIAL_ERROR') else 10)
            # Continue to the beginning of the outer `while True` to re-initialize UART / re-check simulation mode

        except (busio.UART.error, OSError) as e: # Catch specific serial/OS errors.
            err_msg = f"UART/Serial port error: {e}. Please check port '{config.SERIAL_PORT if hasattr(config, 'SERIAL_PORT') else 'N/A'}' and reader connection."
            print(f"ERROR: {err_msg}")
            if uart: # uart might be None if init failed before this point
                try:
                    uart.deinit()
                except Exception as deinit_e:
                    print(f"ERROR: Exception during UART deinit after error: {deinit_e}")
            uart = None # Ensure uart object is reset
            retry_delay = config.RETRY_DELAY_SERIAL_ERROR if hasattr(config, 'RETRY_DELAY_SERIAL_ERROR') else 10
            print(f"INFO: Retrying in {retry_delay} seconds...")
            time.sleep(retry_delay)
        except AttributeError as e: # Handle cases where config attributes are missing mid-loop
            print(f"ERROR: Configuration attribute missing: {e}. Please ensure config.py is complete. Exiting.")
            return # Critical error, exit function
        except Exception as e:
            err_msg = f"An unexpected error occurred in RFID listening loop: {e} (Type: {type(e)})."
            print(f"ERROR: {err_msg}")
            if uart:
                try:
                    uart.deinit()
                except Exception as deinit_e:
                    print(f"ERROR: Exception during UART deinit after unexpected error: {deinit_e}")
            uart = None
            retry_delay = config.RETRY_DELAY_UNEXPECTED_ERROR if hasattr(config, 'RETRY_DELAY_UNEXPECTED_ERROR') else 10
            print(f"INFO: Retrying in {retry_delay} seconds...")
            time.sleep(retry_delay)


if __name__ == '__main__':
    print("INFO: RFID Scrobbler script starting...")
    requests_session = None
    try:
        # Check for essential config attributes on startup
        required_attrs = [
            'LASTFM_API_KEY', 'LASTFM_API_SECRET', 'LASTFM_SESSION_KEY', 'LASTFM_USERNAME',
            'APP_ID', 'TARGET_USER_ID', 'SERIAL_PORT', 'BAUD_RATE', 'RFID_ALBUM_MAPPINGS',
            'RETRY_DELAY_SERIAL_ERROR', 'RETRY_DELAY_UNEXPECTED_ERROR', 'NO_DATA_SLEEP_INTERVAL',
            'WIFI_SSID', 'WIFI_PASSWORD'
        ]
        missing_attrs = [attr for attr in required_attrs if not hasattr(config, attr)]
        if missing_attrs:
            print(f"ERROR: Essential configuration missing in config.py: {', '.join(missing_attrs)}. "
                  "Please create/populate config.py from config_example.py. Exiting.")
            exit()

        # Advisory check for SERIAL_PORT format
        if not (config.SERIAL_PORT == "SIMULATE" or \
                (isinstance(config.SERIAL_PORT, tuple) and len(config.SERIAL_PORT) == 2 and \
                 all(hasattr(pin, "deinit") for pin in config.SERIAL_PORT)) # Basic check for Pin-like objects
               ) :
            print(f"WARN: config.SERIAL_PORT ('{config.SERIAL_PORT}') might not be 'SIMULATE' or a valid tuple of two board.Pin objects. "
                  "Ensure pins are correctly defined in config.py (e.g., using 'import board').")
            # This is a warning; listen_for_rfid_scans will handle errors more definitively.

        # Warning for default Last.fm API key
        if config.LASTFM_API_KEY == "YOUR_LASTFM_API_KEY":
            print("WARN: LASTFM_API_KEY in config.py is set to the default placeholder. Scrobbling will fail until it's updated.")

        # Warning for default App ID and Target User ID
        if config.APP_ID == 'my-rfid-scrobbler' or config.TARGET_USER_ID == 'my-user-id':
             print("WARN: You might be using default APP_ID or TARGET_USER_ID from config_example.py. Update config.py if these are used for specific purposes.")

        # --- WiFi Connection ---
        if hasattr(config, 'WIFI_SSID') and config.WIFI_SSID != "YOUR_WIFI_SSID" and len(config.WIFI_SSID) > 0 :
            print(f"Connecting to WiFi SSID: {config.WIFI_SSID}...")
            try:
                wifi.radio.connect(config.WIFI_SSID, config.WIFI_PASSWORD)
                print("Successfully connected to WiFi.")
                pool = socketpool.SocketPool(wifi.radio)
                requests_session = requests.Session(pool, ssl.create_default_context())
                print("Requests session initialized.")
            except ConnectionError as e:
                print(f"ERROR: WiFi connection failed: {e}")
                print("Continuing without network functionality. Last.fm scrobbling will be disabled.")
                requests_session = None
            except Exception as e:
                print(f"ERROR: An unexpected error occurred during WiFi setup: {e}")
                requests_session = None
        else:
            print("WARN: WiFi SSID not configured in config.py or using default/empty. Skipping WiFi setup.")
            print("Last.fm scrobbling will be disabled.")
            requests_session = None

    except ImportError:
        print("ERROR: config.py not found. Please copy config_example.py to config.py and fill in your details. Exiting.")
        exit()
    except AttributeError as e: # Should be caught by hasattr checks, but as a fallback for config itself
        print(f"ERROR: A required configuration variable is missing or accessed incorrectly: {e}. Please check your config.py. Exiting.")
        exit()

    listen_for_rfid_scans(requests_session)
            # The 'with' statement is removed for now as UART objects in CircuitPython
            # are often used directly and their lifecycle managed differently.
            # The script structure with the `while True` loop for connection attempts is kept.
            # If using the uart object directly, error handling for UART initialization will be needed here.

            # Placeholder for UART communication logic
            # For now, we assume `uart` would be initialized in a real CircuitPython environment.
            # This script will not run correctly without a valid `uart` object.
            # Proper UART initialization and error handling should be added here.
            # e.g. uart = busio.UART(board.GP0, board.GP1, baudrate=config.BAUD_RATE, timeout=1) # Example for Pico

            # Simulating the loop structure that would use the uart object
            # To make the script runnable for testing other parts, we'll mock a readline if uart is not defined.
            # In a real deployment, `uart` must be initialized above.
            # uart = None # This should be initialized inside the try block for serial connection

            # This section related to log_to_firestore calls needs to be removed or replaced with print.
            # try:
            #     # TODO: Replace board.TX and board.RX with your ESP32's specific UART pins
            #     uart = busio.UART(board.TX, board.RX, baudrate=config.BAUD_RATE, timeout=1) # Attempt initialization
            #     connect_msg = f"Successfully connected to RFID reader on {config.SERIAL_PORT} (using busio.UART). Waiting for scans..."
            #     print(f"INFO: {connect_msg}")
            # except NameError: # board.TX or board.RX might not be defined if 'board' is not the actual CircuitPython board library
            #     print(f"WARN: busio.UART not initialized (board.TX/RX not found). RFID reading will be simulated if config.SERIAL_PORT is 'SIMULATE'.")
            # except RuntimeError as e: # Catch other UART init errors e.g. pins already in use
            #     print(f"ERROR: Failed to initialize UART: {e}. RFID reading will be simulated if config.SERIAL_PORT is 'SIMULATE'.")

            # The main logic for UART initialization and read loop is handled in the preceding change block.
            # This section is now focused on removing Firestore logging calls from the template that was pasted.
            # The actual logic for reading from UART or SIMULATE mode is already in place from previous diffs.
            # We just need to ensure all log_to_firestore calls are removed.

            # Example of a log_to_firestore call that needs to be removed/replaced:
            # log_to_firestore(db, APP_ID, scan_msg, type='scan', details={'rfid_tag': tag_id})
            # Becomes:
            # print(f"INFO: Tag Scanned: {tag_id}")

            # Another example:
            # log_to_firestore(db, APP_ID, err_msg_scrobble, type='warning', details={'rfid_tag': tag_id})
            # Becomes:
            # print(f"WARN: {err_msg_scrobble}")

            # The actual implementation of the RFID reading loop, including the new config loading,
            # UART/simulation logic, and replacement of log_to_firestore with print(),
            # has been applied in the diff block that modified the `listen_for_rfid_scans` function extensively.
            # This current diff block is primarily for ensuring all remnants of old configuration
            # and Firebase-specific code are cleaned up, especially the global variable definitions
            # and the Firebase initialization block.

            # The __main__ block below will also be updated to remove db dependencies and use config.
            pass # Placeholder as the main changes are in listen_for_rfid_scans and __main__


if __name__ == '__main__':
    print("INFO: RFID Scrobbler script starting...")
    try:
        # Check for essential config attributes on startup
        required_attrs = [
            'LASTFM_API_KEY', 'LASTFM_API_SECRET', 'LASTFM_SESSION_KEY', 'LASTFM_USERNAME',
            'APP_ID', 'TARGET_USER_ID', 'SERIAL_PORT', 'BAUD_RATE', 'RFID_ALBUM_MAPPINGS'
        ]
        missing_attrs = [attr for attr in required_attrs if not hasattr(config, attr)]
        if missing_attrs:
            print(f"ERROR: Essential configuration missing in config.py: {', '.join(missing_attrs)}. "
                  "Please create/populate config.py from config_example.py. Exiting.")
            exit()

        # Warning for default Last.fm API key
        if config.LASTFM_API_KEY == "YOUR_LASTFM_API_KEY":
            print("WARN: LASTFM_API_KEY in config.py is set to the default placeholder. Scrobbling will fail until it's updated.")

        # Warning for default App ID and Target User ID
        if config.APP_ID == 'my-rfid-scrobbler' or config.TARGET_USER_ID == 'my-user-id':
             print("WARN: You might be using default APP_ID or TARGET_USER_ID from config_example.py. Update config.py if these are used for specific purposes.")

    except ImportError:
        print("ERROR: config.py not found. Please copy config_example.py to config.py and fill in your details. Exiting.")
        exit()
    # AttributeError should be caught by hasattr checks above, but as a fallback:
    except AttributeError as e:
        print(f"ERROR: A required configuration variable is missing or accessed incorrectly in config.py: {e}. Please check your config.py. Exiting.")
        exit()

    listen_for_rfid_scans()

