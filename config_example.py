# Last.fm API Credentials
LASTFM_API_KEY = "YOUR_LASTFM_API_KEY"
LASTFM_API_SECRET = "YOUR_LASTFM_API_SECRET"
LASTFM_SESSION_KEY = "YOUR_LASTFM_SESSION_KEY" # Obtained after user authorization
LASTFM_USERNAME = "YOUR_LASTFM_USERNAME"

# Application and User Identifiers (if still needed for other purposes, otherwise can be removed)
APP_ID = 'my-rfid-scrobbler'
TARGET_USER_ID = 'my-user-id' # Or link this to LASTFM_USERNAME if they are the same

# Serial Port for RFID Reader
# For CircuitPython on microcontrollers, this should be a tuple of (TX_PIN, RX_PIN)
# using 'board' module pins. The pins must be actual board.Pin objects.
# Example for ESP32-S3 (check your board's specific pin names):
# import board
# SERIAL_PORT = (board.TX, board.RX) # Or e.g. (board.IO43, board.IO44) if using a secondary UART
#
# To use specific pins, you MUST import 'board' in your actual config.py and assign the pins.
# e.g., in your config.py:
#   import board
#   SERIAL_PORT = (board.GP0, board.GP1) # For Raspberry Pi Pico
#   SERIAL_PORT = (board.IO1, board.IO2) # For a generic ESP32, replace IO1/IO2
#
# Set to "SIMULATE" for testing without actual hardware (reads from console input).
SERIAL_PORT = "SIMULATE"
BAUD_RATE = 9600

# RFID Tag to Album Mappings
# Format: "RFID_TAG_ID": {"artist": "Artist Name", "album": "Album Name"}
RFID_ALBUM_MAPPINGS = {
    "1234567890": {"artist": "Example Artist", "album": "Example Album"},
    "another_tag_id": {"artist": "Another Artist", "album": "Another Album Vol. 1"},
    # Add more mappings here
}

# WiFi credentials
WIFI_SSID = "YOUR_WIFI_SSID"
WIFI_PASSWORD = "YOUR_WIFI_PASSWORD"

# Power Saving / Retry Delays
RETRY_DELAY_SERIAL_ERROR = 10  # Seconds to wait before retrying serial connection/setup issues
RETRY_DELAY_UNEXPECTED_ERROR = 10 # Seconds to wait after an unexpected error in the main loop
NO_DATA_SLEEP_INTERVAL = 0.1 # Seconds to sleep if no data from UART (helps reduce busy-waiting)
