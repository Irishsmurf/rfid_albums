Vinyl Scrobbler Project README

This project allows you to scan an RFID tag on a vinyl record sleeve and have the entire album scrobbled to your Last.fm account.

It consists of two main parts: a web application for configuration and logging, and a Python script that reads the RFID tags.

Part 1: The Web Application
The web app is a single HTML file that you can host on a service like GitHub Pages or Netlify. It is used to:

Configure your Firebase project settings.

Enter your Last.fm API Key, Secret, and Username.

Authorize the app with your Last.fm account.

Map your RFID tag IDs to specific albums (Artist and Album Title).

View a real-time log of scans and scrobbles.

Setup for the Web App:

Create a project in the Firebase Console.

In your Firebase project, go to the "Authentication" section, click the "Sign-in method" tab, and enable the "Anonymous" provider.

In your Firebase project settings, find your web app's configuration object. It's a block of JSON.

Open the web app, paste this Firebase config JSON into the "Firebase Setup" section, and save. The app will save this to your browser's local storage.

Create a Last.fm API account to get an API Key and Secret.

Enter your Last.fm credentials into the web app and save.

Click "Authenticate with Last.fm" and authorize the application.

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