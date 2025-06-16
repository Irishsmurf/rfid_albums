Vinyl Scrobbler Project README

This project allows you to scan an RFID tag on a vinyl record sleeve and have the entire album scrobbled to your Last.fm account. It also supports scanning album barcodes to automatically fetch artist and album details using the Discogs API.

It consists of two main parts: a web application for configuration and logging, and a Python script that reads the RFID tags.

## Features

*   **RFID-Based Scrobbling:** Scan an RFID tag on your record sleeve to trigger scrobbling.
*   **Barcode Scanning:** Scan an album's barcode to automatically look up and populate Artist and Album Name fields using the Discogs API.
*   **Real-time Updates:** Uses Firebase Firestore for real-time communication between the RFID reader and the web app, and for live logging.
*   **Last.fm Integration:** Securely connects to your Last.fm account to scrobble played tracks.
*   **Album Mapping:** Manually map RFID tags to specific albums if needed.
*   **Web-Based Interface:** All configuration, mapping, and logging are handled through an easy-to-use web interface.

Part 1: The Web Application
The web app is a single HTML file that you can host on a service like GitHub Pages or Netlify. It is used to:

Configure your Firebase project settings.

Enter your Last.fm API Key, Secret, and Username.

Authorize the app with your Last.fm account.

Optionally, enter a Discogs Personal Access Token for improved barcode lookup.

Map your RFID tag IDs to specific albums (Artist and Album Title), or use barcode scanning to populate these fields.

View a real-time log of scans and scrobbles.

**Using Barcode Scanning:**
1.  Navigate to the "3. Album Collection" section in the web app.
2.  Click the "Scan Barcode" button.
3.  If prompted by your browser, grant camera access.
4.  Position your album sleeve's barcode in front of the camera, within the designated scanning area.
5.  Once the barcode is successfully scanned, the app will attempt to fetch album details from Discogs.
6.  If found, the "Artist Name" and "Album Name" fields will be automatically populated. You can then add an RFID tag ID and save this mapping.

Setup for the Web App:

Create a project in the Firebase Console.

In your Firebase project, go to the "Authentication" section, click the "Sign-in method" tab, and enable the "Anonymous" provider.

In your Firebase project settings, find your web app's configuration object. It's a block of JSON.

Open the web app, paste this Firebase config JSON into the "Firebase Setup" section, and save. The app will save this to your browser's local storage.

Create a Last.fm API account to get an API Key and Secret.

Enter your Last.fm credentials into the web app and save.

Click "Authenticate with Last.fm" and authorize the application.

**Discogs Integration (Optional, but Recommended for Barcode Scanning):**
For the barcode scanning feature to reliably fetch album details, it's recommended to use the Discogs API. You'll need a Personal Access Token from Discogs:
1.  Log in to your Discogs account.
2.  Go to your Developer Settings page: [https://www.discogs.com/settings/developers](https://www.discogs.com/settings/developers).
3.  Click the "Generate new token" button.
4.  Copy the generated token.
5.  In the Vinyl Scrobbler web app, go to the "1.B Discogs API Settings" section.
6.  Paste your token into the "Discogs Personal Access Token" field and click "Save Discogs Token".
While barcode lookup might work for some queries without a token, frequent use or enhanced reliability requires a token.

Part 2: The Python RFID Reader Script
The Python script runs on a computer (like a Raspberry Pi) connected to a USB RFID reader.

Prerequisites:
You must install the required Python libraries:
pip install pyserial firebase-admin

Setup for the Python Script:
The script is configured using environment variables for security.

FIREBASE_SERVICE_ACCOUNT_B64:

In your Firebase project settings, go to "Service accounts" and generate a new private key. This will download a JSON file.

Convert this JSON file to a Base64 string.

On macOS/Linux: base64 serviceAccountKey.json

On Windows (PowerShell): [Convert]::ToBase64String([IO.File]::ReadAllBytes("serviceAccountKey.json"))

Set this Base64 string as an environment variable named FIREBASE_SERVICE_ACCOUNT_B64.

APP_ID:

This is your Firebase Project ID. You can find it in your Firebase project settings.

Set it as an environment variable named APP_ID.

SERIAL_PORT:

This is the port your RFID reader is connected to (e.g., /dev/ttyUSB0 on Linux, COM3 on Windows).

Set it as an environment variable named SERIAL_PORT.

Running the script:
Once the environment variables are set, run the script from your terminal:
python your_script_name.py

How It Works
You scan a record's RFID tag.

The Python script reads the tag ID and writes it to a 'scans' collection in Firestore.

The web app, which is listening for changes, gets an instant notification from Firestore.

The web app looks up the RFID tag in its 'albums' collection to find the artist and title.

The web app calls the Last.fm API to get the album's tracklist.

The web app then calls the Last.fm API again to scrobble every track on the album.