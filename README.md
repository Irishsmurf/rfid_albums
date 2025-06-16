
# Vinyl Scrobbler for Last.fm

## Overview

The Vinyl Scrobbler project allows you to connect a physical action – scanning an RFID tag on a vinyl record sleeve – with your digital music listening history on Last.fm. By waving your tagged record near an RFID reader, the entire album is automatically scrobbled to your Last.fm account.

This system comprises two main components:
1.  A Python script that runs on a computer (like a Raspberry Pi) connected to a USB RFID reader.
2.  A web application (a single `index.html` file) used for initial setup, configuration (Firebase, Last.fm), mapping RFID tags to albums, and viewing real-time scan/scrobble logs.

## Features

- **RFID Tag Scanning:** Detects RFID tags using a USB reader connected to a Python script.
- **Last.fm Integration:** Scrobbles entire albums (all tracks) to your Last.fm account.
- **Web Interface:** A user-friendly web application (`index.html`) for:
    - Firebase project configuration.
    - Securely entering and saving Last.fm API credentials (API Key, Secret, Username).
    - Authenticating the application with your Last.fm account.
    - Mapping RFID tag IDs to specific albums (Artist and Album Title).
    - Viewing a collection of your mapped albums.
    - Real-time logging of RFID scans, Last.fm API interactions, and scrobbling status.
- **Firebase Backend:** Uses Firestore to:
    - Communicate scanned RFID tag IDs from the Python script to the web application.
    - Store Last.fm API settings and session keys.
    - Store the user's album collection (RFID tag to album mappings).
- **Anonymous Authentication:** Simple user identification in Firebase for storing personalized settings.
- **Dynamic Tracklist Fetching:** Retrieves album tracklists from Last.fm before scrobbling.

## How It Works

The project operates through a coordinated effort between the Python RFID reader script and the web application, mediated by Firebase Firestore:

1.  **RFID Tag Scan:** You scan an RFID tag attached to a vinyl record using the USB RFID reader.
2.  **Python Script Action:**
    *   The `rfid_reader.py` script, running on a computer connected to the reader, continuously listens for serial input.
    *   Upon detecting a tag ID, the script sends this ID to a specific collection in your Firebase Firestore database (under `artifacts/<YOUR_APP_ID>/public/data/scans`).
3.  **Web Application Listener:**
    *   The `index.html` web application, once configured and running in your browser, actively listens for new documents added to that same 'scans' collection in Firestore.
4.  **Album Lookup & Scrobbling:**
    *   When a new scan (RFID ID) appears, the web app is notified.
    *   It first checks if this RFID ID exists in its 'albums' collection (stored in Firestore at `artifacts/<YOUR_APP_ID>/public/data/albums/<RFID_ID>`). This collection maps RFID IDs to artist and album names.
    *   **If the RFID ID is known:** The web app uses the Last.fm API to:
        1.  Fetch the full tracklist for the mapped album and artist.
        2.  Scrobble each track from the album to your Last.fm account. Timestamps are adjusted to reflect a typical album listening session.
    *   **If the RFID ID is unknown:** The web app will typically populate the "RFID Tag ID" field in the "Album Collection" section, allowing you to map it to an artist and album.
5.  **Logging:** Both the Python script (to its console) and the web application (in the "Scrobble Log" section) provide real-time feedback on the process, including successful scans, Firebase communication, Last.fm API calls, and any errors encountered.
6.  **Data Cleanup:** After processing a scan from the `scans` collection, the web application deletes the document to prevent re-processing.

## Prerequisites

To set up and run the Vinyl Scrobbler, you will need:

- **Hardware:**
    - A USB RFID reader (e.g., a common 125kHz EM4100 reader or similar that can output tag IDs via a serial connection).
    - RFID tags to attach to your vinyl record sleeves.
    - A computer to run the Python script and connect to the RFID reader (e.g., a Raspberry Pi, laptop).

- **Software & Accounts:**
    - **Python 3.x:** Ensure Python 3 is installed on the computer that will run `rfid_reader.py`.
    - **pip:** The Python package installer, usually included with Python.
    - **Firebase Project:**
        - A free Firebase project. You can create one at [console.firebase.google.com](https://console.firebase.google.com/).
    - **Last.fm Account:**
        - A Last.fm user account.
        - A Last.fm API account to obtain an **API Key** and **API Secret**. You can create one at [www.last.fm/api/account/create](https://www.last.fm/api/account/create).
    - **Serial Port Identifier:** You'll need to know the serial port name your RFID reader uses (e.g., `/dev/ttyUSB0` on Linux, `COM3` on Windows).

## Setup

### Web Application Setup

The web application (`index.html`) is your control panel for configuration and logging.

1.  **Create a Firebase Project:**
    *   Go to the [Firebase Console](https://console.firebase.google.com/) and create a new project (or use an existing one).
2.  **Enable Anonymous Authentication:**
    *   In your Firebase project, navigate to "Authentication" (under Build).
    *   Click the "Sign-in method" tab.
    *   Select "Anonymous" from the providers list and enable it.
3.  **Get Firebase Web App Configuration:**
    *   In your Firebase project settings (click the gear icon next to "Project Overview"):
        *   Scroll down to "Your apps".
        *   If you don't have a web app, click the web icon (`</>`) to create one.
        *   Find your web app's configuration object (Firebase SDK snippet). It's a JavaScript object that looks like this:
            ```javascript
            const firebaseConfig = {
              apiKey: "AIza...",
              authDomain: "YOUR_PROJECT_ID.firebaseapp.com",
              projectId: "YOUR_PROJECT_ID",
              storageBucket: "YOUR_PROJECT_ID.appspot.com",
              messagingSenderId: "...",
              appId: "...",
              measurementId: "..." // Optional
            };
            ```
4.  **Configure the Web App (`index.html`):**
    *   Open `index.html` in your web browser (e.g., by double-clicking the file).
    *   Under the "0. Firebase Setup (Required)" section, you will find a text area labeled "Firebase Config (JSON)".
    *   Paste the entire `firebaseConfig` JavaScript object (from step 3) into this text area.
    *   Click the "Save & Initialize Firebase" button.
    *   The status message below the button should change to "Status: Initialized (Project ID: YOUR_PROJECT_ID)". If it shows an error, double-check the pasted configuration.
5.  **Create a Last.fm API Account:**
    *   If you don't have one, go to the [Last.fm API page](https://www.last.fm/api/account/create) and apply for an API account. You'll receive an **API Key** and **Shared Secret**.
6.  **Configure Last.fm API Settings in Web App:**
    *   In the web app, go to the "1. Last.fm API Settings" section.
    *   Enter your Last.fm **API Key**, **API Secret**, and your **Last.fm Username**.
    *   Click "Save Settings".
7.  **Authorize with Last.fm:**
    *   Click the "Authenticate with Last.fm" button. This will redirect you to Last.fm to grant permission.
    *   After authorizing, you'll be redirected back to the web app. The status should change to "Status: Authenticated as [YourUsername]".
### Python RFID Reader Script Setup

The Python script (`rfid_reader.py`) reads tag IDs from your RFID reader and sends them to Firebase.

1.  **Install Python Libraries:**
    *   Open your terminal or command prompt.
    *   Install the necessary libraries using pip:
        ```bash
        pip install pyserial firebase-admin
        ```

2.  **Configure Firebase Admin SDK:**
    *   In your Firebase project settings, navigate to "Service accounts".
    *   Click "Generate new private key" and a JSON file will be downloaded.
    *   **Crucial:** Rename this downloaded JSON file to **`serviceAccountKey.json`**.
    *   Place this **`serviceAccountKey.json`** file in the **same directory** as the `rfid_reader.py` script. The script is hardcoded to look for **`serviceAccountKey.json`** in its local directory.

3.  **Configure Script Variables directly in `rfid_reader.py`:**
    *   Open `rfid_reader.py` in a text editor. You will need to modify the following variables at the top of the script:
    *   **`APP_ID` (Firebase Project ID)**:
        *   Locate the line: `APP_ID = 'default-scrobbler-app'`
        *   **You MUST change `'default-scrobbler-app'` to your actual Firebase Project ID.**
        *   This `APP_ID` variable in the script must exactly match the `projectId` value from your Firebase web app configuration (the `firebaseConfig` object you pasted into `index.html`).
        *   **Note:** The web app's footer displays "Your User ID for sharing/syncing", which is your unique *Firebase User ID (uid)* for anonymous authentication, **not** the *Firebase Project ID* required for this `APP_ID` variable.
    *   **`SERIAL_PORT`**:
        *   Locate the line: `SERIAL_PORT = '/dev/ttyUSB0'`
        *   Change `'/dev/ttyUSB0'` to the correct serial port for your RFID reader on your system (e.g., `COM3` on Windows, or a different `/dev/tty...` path on Linux/macOS).
    *   **`BAUD_RATE`** (Optional):
        *   Locate the line: `BAUD_RATE = 9600`
        *   The default baud rate of 9600 is common for many RFID readers. Only change this if you are certain your reader uses a different baud rate.

    *   **(Note on Environment Variables):**
        *   Previous project documentation mentioned using environment variables for these settings. However, the current `rfid_reader.py` script is set up for direct modification of its variables and expects `serviceAccountKey.json` locally. If you prefer environment variables, you would need to modify the script's logic for configuration loading. For the current version, follow the steps above.

## Running the Project

After completing the setup for both components:

### 1. Web Application

*   **Open `index.html`:** Simply open the `index.html` file in a modern web browser (e.g., Chrome, Firefox, Edge, Safari).
*   **Check Configuration:**
    *   Ensure the Firebase status shows "Initialized" with your Project ID. If not, revisit the "Firebase Setup" in the web app.
    *   Ensure the Last.fm status shows "Authenticated". If not, try saving your API settings again and re-authenticating.
*   The web application needs to remain open in your browser to listen for scans and perform scrobbling.
### 2. Python RFID Reader Script

*   **Verify Setup:**
    *   Double-check that you have correctly placed the `serviceAccountKey.json` file in the same directory as `rfid_reader.py`.
    *   Ensure you have updated the `APP_ID` and `SERIAL_PORT` variables within the `rfid_reader.py` script.
*   **Connect RFID Reader:** Make sure your USB RFID reader is connected to the computer.
*   **Run from Terminal:**
    *   Navigate to the directory containing `rfid_reader.py` in your terminal or command prompt.
    *   Execute the script:
        ```bash
        python rfid_reader.py
        ```
*   **Monitor Output:**
    *   The script will attempt to connect to Firebase and the serial port.
    *   Look for "Successfully connected to Firebase." and "Successfully connected to reader. Waiting for scans..." messages.
    *   If there are errors (e.g., "Could not open serial port"), follow the troubleshooting advice in the script's output or the "Troubleshooting" section below.
    *   Keep this script running in the terminal to continuously listen for RFID scans.

## Usage

Once both the web application and the Python RFID reader script are set up and running:

1.  **Open the Web Application:** Have `index.html` open in your browser. This is where you'll manage albums and see logs.
2.  **Map Your Albums (if not already done):**
    *   Take a record with an RFID tag. Scan the tag.
    *   The RFID ID will appear in the "RFID Tag ID" field in the "2. Album Collection" section of the web app. It might also log a message like "RFID tag [ID] is not in your collection."
    *   Enter the "Artist Name" and "Album Name" for this tag.
    *   Click "Add Album to Collection". The album will appear in the "Your Albums" list.
    *   Repeat for all records you want to scrobble.
3.  **Scrobble a Record:**
    *   Simply scan an RFID tag that you have already added to your Album Collection.
    *   **Observe the Python Script:** The terminal running `rfid_reader.py` should show "--- Tag Scanned: [ID] ---" and "Successfully sent tag ID to Firebase".
    *   **Observe the Web Application:**
        *   The "Scrobble Log" will show messages like:
            *   "Received scan for RFID: [ID]"
            *   "Found album: [Album Name] by [Artist Name]"
            *   "Fetching tracklist for [Album Name] by [Artist Name]..."
            *   "Found [X] tracks. Scrobbling now..."
            *   "Successfully scrobbled [Y] tracks for '[Album Name]'!"
        *   If the tag is not in your collection, it will log a message indicating this, and you can add it using the "Album Collection" section.
4.  **Check Last.fm:** Your Last.fm profile should now show the scrobbled tracks from the album. Note that Last.fm might take a few moments to update.

## Troubleshooting

Here are some common issues and how to resolve them:

**Web Application (`index.html`):**

*   **"Status: Not Initialized" under Firebase Setup:**
    *   **Cause:** The Firebase configuration JSON is incorrect, missing, or could not be parsed.
    *   **Solution:**
        1.  Carefully re-copy the Firebase config object from your Firebase project settings.
        2.  Ensure it's pasted correctly into the "Firebase Config (JSON)" text area in the web app.
        3.  Make sure it's valid JSON (e.g., no trailing commas if you manually edited it).
        4.  Click "Save & Initialize Firebase" again. Check the browser's developer console (usually F12) for more specific error messages.
*   **Last.fm Authentication Fails or "Status: Not Authenticated":**
    *   **Cause:** Incorrect API Key, API Secret, or Last.fm Username; or Last.fm authentication process was not completed.
    *   **Solution:**
        1.  Double-check your Last.fm API Key, API Secret, and Username in the "1. Last.fm API Settings" section. Ensure there are no extra spaces.
        2.  Click "Save Settings" after entering them.
        3.  Click "Authenticate with Last.fm" and ensure you complete the authorization on the Last.fm website.
        4.  Check the browser's developer console for error messages from the Last.fm API.
*   **Scans appear in Python script console but not in Web App Log:**
    *   **Cause:** The `APP_ID` variable in `rfid_reader.py` does not match the `projectId` from the `firebaseConfig` used by the web application. Firestore rules could also be an issue, but this is less common with the default anonymous authentication setup.
    *   **Solution:**
        1.  **Crucial Check:** Confirm that the value of the `APP_ID` variable in your `rfid_reader.py` script is identical to the `projectId` value within the `firebaseConfig` object you pasted into the web application's "Firebase Config (JSON)" field.
        2.  In the Firebase console for your project, navigate to "Firestore Database". When you scan a tag, check if a new document appears in the `artifacts/<YOUR_PROJECT_ID>/public/data/scans` collection (replace `<YOUR_PROJECT_ID>` with your actual Project ID).
            *   If data appears here, the Python script is correctly sending data. The issue is likely with the web app's connection or listener for this specific path.
            *   If data does *not* appear here, the Python script is likely misconfigured (wrong `APP_ID` or `serviceAccountKey.json` issue) or failing to send data.
*   **"Album mapping for [ID] deleted" or albums disappear unexpectedly:**
    *   **Cause:** The web app has a "Delete" button for albums in the "Your Albums" list. It might have been clicked accidentally.
    *   **Solution:** Re-add the album mapping if it was an accident.

**Python RFID Reader Script (`rfid_reader.py`):**

*   **"ERROR: Could not initialize Firebase. Make sure 'serviceAccountKey.json' is correct."**
    *   **Cause:** The **`serviceAccountKey.json`** file is missing, in the wrong directory, named incorrectly, or not a valid service account key.
    *   **Solution:**
        1.  Ensure you downloaded the private key JSON file from your Firebase project's "Service accounts" settings.
        2.  Confirm it is named exactly **`serviceAccountKey.json`**.
        3.  Verify that **`serviceAccountKey.json`** is located in the *same directory* as your `rfid_reader.py` script. The script looks for it there.
*   **"Error: Could not open serial port [your_port_name]."**
    *   **Cause:** The `SERIAL_PORT` variable in `rfid_reader.py` is incorrect, the reader is not connected, or you don't have permission to access it.
    *   **Solution:**
        1.  Verify the RFID reader is plugged into your computer.
        2.  Check your system's device manager (Windows) or use commands like `ls /dev/tty*` (Linux/macOS) to find the correct port name.
        3.  Update the `SERIAL_PORT` variable in `rfid_reader.py` with the correct port.
        4.  On Linux, you might need to add your user to the `dialout` group (e.g., `sudo usermod -a -G dialout yourusername`) and then log out/in.
*   **Script runs but no tags are detected:**
    *   **Cause:** RFID reader might not be compatible, wrong baud rate, or issues with the tag itself.
    *   **Solution:**
        1.  Ensure your RFID reader outputs tag IDs as simple serial data.
        2.  The default `BAUD_RATE = 9600` is common, but check if your reader uses a different one.
        3.  Try a different RFID tag.
        4.  Test the reader with other serial terminal software (like PuTTY, CoolTerm, or even `screen` on macOS/Linux) to see if it's outputting data when a tag is scanned.

**General Issues:**

*   **Scrobbles Not Appearing on Last.fm:**
    *   **Cause:** Incorrect Last.fm API credentials, Last.fm session expired, or Last.fm API issues.
    *   **Solution:**
        1.  In the web app, re-verify Last.fm API settings and try re-authenticating.
        2.  Check the "Scrobble Log" in the web app for specific error messages from Last.fm.
        3.  Last.fm sometimes has delays; wait a few minutes.

## Contributing

Contributions are welcome! Please fork the repository and submit a pull request with your suggested changes.

## License

The license for this project is not specified. If you intend to share or distribute this project publicly, it's recommended to add a `LICENSE` file to the repository (e.g., choosing a common open-source license like the MIT License).
