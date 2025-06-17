# ESP32 RFID Music Scrobbler with Last.fm & Firebase

A project that uses an ESP32 with an RFID reader to scan tags, publish them to MQTT, and trigger a Google Cloud Function. The Cloud Function then scrobbles the associated album to Last.fm and logs activities to Firebase Firestore. A web UI is provided for managing RFID-album associations, viewing logs, and configuring Last.fm authentication.

## Features

*   **ESP32 RFID Reader:** Scans RFID tags using CircuitPython.
*   **Low Power:** Button-triggered operation and deep sleep on the ESP32.
*   **MQTT Communication:** Publishes scanned RFID tags to an MQTT broker.
*   **Cloud Processing:** Google Cloud Function (Python) processes tags from Pub/Sub.
    *   Fetches album details from Firebase Firestore.
    *   Authenticates with Last.fm API.
    *   Scrobbles complete albums (all tracks) to a designated Last.fm user account.
    *   Logs all significant actions and errors to Firestore.
*   **Web UI Management Console:**
    *   Manages RFID tag to Artist/Album associations in Firestore (Google).
    *   Displays system logs from Firestore (from ESP32 via Cloud Function, and Cloud Function itself).
    *   Allows configuration of Last.fm API credentials (application's key/secret).
    *   Initiates the Last.fm user authentication flow to obtain a session key for scrobbling.

## System Architecture (Conceptual)

```
+-------+     MQTT     +-------------+     Pub/Sub    +-----------------+     +--------------+
| ESP32 |------------->| MQTT Broker |--------------->| Google Pub/Sub  |---->| Cloud Function |------> Last.fm API
+-------+              +-------------+   (via bridge*)|                 |     +-----------------+        /|                                         or direct    +-----------------+            |             |
                                                                                     |             | (Firestore)
                                                                                     V             |
+-----------------+                                                            +-------------------+
| Web UI (Admin)  |<----------------------------------------------------------->| Firebase Firestore|
+-----------------+                                                            +-------------------+
```
_*Note on MQTT Bridge: The ESP32 script currently uses standard MQTT. A bridge component may be needed to relay messages to Google Cloud Pub/Sub if not publishing directly to a Google Cloud IoT Core MQTT endpoint._

## Components

### 1. ESP32 CircuitPython Script (`esp32_rfid_mqtt.py`)

*   **Purpose:** Wakes on button press, reads an RFID tag, connects to Wi-Fi, publishes the tag ID to an MQTT topic, and goes back to deep sleep.
*   **Hardware:**
    *   ESP32 microcontroller board.
    *   RFID Reader: Currently assumes a generic UART-based reader. For other readers (e.g., MFRC522, PN532), specific CircuitPython libraries and code adjustments are needed.
    *   A physical button for wake-up.
*   **Pin Configuration (in `esp32_rfid_mqtt.py` - adjust as needed):**
    *   `BUTTON_PIN`: Pin connected to the wake-up button (e.g., `board.IO0`).
    *   `RFID_RX_PIN`, `RFID_TX_PIN`: UART pins for the RFID reader (e.g., `board.IO1`, `board.IO2`).
*   **Software:**
    *   CircuitPython for ESP32.
    *   Required CircuitPython libraries (place in `lib` folder on ESP32):
        *   `adafruit_minimqtt` (and its dependencies)
        *   Any specific RFID reader libraries if not using generic UART.
*   **Configuration (`secrets.py`):** Create this file in the root of the ESP32's `CIRCUITPY` drive.
    ```python
    secrets = {
        'ssid': 'YOUR_WIFI_SSID',
        'password': 'YOUR_WIFI_PASSWORD',
        'mqtt_broker': 'YOUR_MQTT_BROKER_ADDRESS', # e.g., 'test.mosquitto.org' or your private broker
        'mqtt_port': 1883, # Or 8883 for TLS
        'mqtt_username': 'YOUR_MQTT_USERNAME', # Optional, if broker requires auth
        'mqtt_password': 'YOUR_MQTT_PASSWORD', # Optional
        'mqtt_topic': 'esp32/rfid_tags', # Topic to publish tags to
        # 'aio_username': '', # Not used directly by this project's core logic
        # 'aio_key': '',      # Not used directly
    }
    ```
*   **Setup:**
    1.  Install CircuitPython on your ESP32.
    2.  Copy `esp32_rfid_mqtt.py` to the ESP32 (e.g., as `code.py`).
    3.  Create `secrets.py` on the ESP32 with your credentials.
    4.  Install required libraries into the `lib` folder on the ESP32.

### 2. Google Cloud Function (`cloud_function/`)

*   **Purpose:** Triggered by Pub/Sub messages containing RFID tags. Fetches album data from Firestore, Last.fm credentials from Firestore, scrobbles the album to Last.fm, and logs results.
*   **Trigger:** Google Cloud Pub/Sub.
*   **Runtime:** Python (e.g., Python 3.9).
*   **Files:**
    *   `main.py`: Function logic.
    *   `requirements.txt`: Python dependencies (`firebase-admin`, `requests`, `google-cloud-pubsub`).
*   **Environment Variables (to be set during deployment):**
    *   `APP_ID`: Your application identifier (e.g., `your-rfid-scrobbler`). Must match `APP_ID` in Web UI and Firestore paths.
    *   `TARGET_USER_ID`: The Firebase User ID (or any unique ID) for whom scrobbles will be performed and Last.fm credentials stored. This ID is displayed in the Web UI for reference.
    *   `GOOGLE_APPLICATION_CREDENTIALS`: (Optional if using default service account) Path to service account key JSON. Cloud Functions usually use the runtime service account's default credentials.
*   **Deployment (Example using `gcloud`):**
    ```bash
    gcloud functions deploy rfid_scrobbler_function \
        --runtime python39 \
        --trigger-topic YOUR_PUBSUB_TOPIC_NAME \
        --entry-point rfid_scrobbler_function \
        --source ./cloud_function \
        --set-env-vars APP_ID=your-app-id,TARGET_USER_ID=your-target-user-id \
        --region YOUR_GCP_REGION
    ```
    (Replace placeholders with your actual values.)
*   **IAM Permissions:** The Cloud Function's service account needs roles/permissions for:
    *   Firestore: Read/Write access to relevant paths.
    *   Pub/Sub: Subscriber role for the trigger topic (usually configured automatically).

### 3. Web UI (`web_ui/`)

*   **Purpose:** Manage RFID-album mappings, view logs, and configure Last.fm credentials.
*   **Files:** `index.html`, `css/style.css`, `js/app.js`, `js/firebase-config.js`.
*   **Setup:**
    1.  **Firebase Configuration:** Update `web_ui/js/firebase-config.js` with your Firebase project's web app configuration details.
    2.  **Application IDs:** In `web_ui/js/app.js`, set:
        *   `APP_ID`: Must match the `APP_ID` used in the Cloud Function.
        *   `TARGET_USER_ID`: Must match the `TARGET_USER_ID` in the Cloud Function. This is the user whose Last.fm credentials will be configured via this UI.
    3.  **Serving:** Open `web_ui/index.html` directly in a browser (for local file access, some browser features might be restricted) or deploy it to a static web host (e.g., Firebase Hosting, Netlify, GitHub Pages).
*   **Last.fm Authentication Note:** The Web UI provides fields to store your Last.fm API Key and Secret (which the Cloud Function will use). It also has a placeholder to initiate the Last.fm user authentication flow to get a session key for the `TARGET_USER_ID`. **The full OAuth-like redirect flow for session key generation needs to be implemented in `js/app.js`.**

### 4. Firebase Firestore

*   **Purpose:** Stores album data, Last.fm configurations, and system logs.
*   **Key Data Structures (paths are relative to Firestore root):**
    *   **Albums:** `artifacts/{APP_ID}/public/data/albums/{rfid_tag_id}`
        *   Fields: `artist` (string), `album` (string), `rfid_tag` (string), `updatedAt` (timestamp).
    *   **Last.fm App Config (for `TARGET_USER_ID`):** `artifacts/{APP_ID}/users/{TARGET_USER_ID}/config/lastfm`
        *   Fields: `apiKey` (string), `apiSecret` (string), `updatedAt` (timestamp).
    *   **Last.fm User Session (for `TARGET_USER_ID`):** `artifacts/{APP_ID}/users/{TARGET_USER_ID}/config/lastfm_session`
        *   Fields: `sessionKey` (string), `name` (string - Last.fm username), `updatedAt` (timestamp).
    *   **Logs:** `artifacts/{APP_ID}/public/data/script_logs/{auto_generated_log_id}`
        *   Fields: `timestamp` (timestamp), `message` (string), `type` (string: 'info', 'error', 'scan', etc.), `source` (string: 'cloud_function', 'esp32'), `details` (object, optional), `rfid_tag` (string, optional).
*   **Security Rules:** Configure Firestore security rules to allow appropriate access:
    *   Cloud Function: Needs read/write access to all specified paths using its service account.
    *   Web UI:
        *   Public read for logs might be acceptable.
        *   Authenticated admin access (if you implement user login for the UI) for album management and Last.fm config is recommended.
        *   Example (very basic, **review and tighten for production!**):
            ```json
            rules_version = '2';
            service cloud.firestore {
              match /databases/{database}/documents {
                // Allow public read for logs and albums for simplicity, restrict writes
                match /artifacts/{appId}/public/data/{coll}/{docId} {
                  allow read: if true;
                  allow write: if request.auth != null; // Example: only authenticated users
                }
                // Restrict user-specific config
                match /artifacts/{appId}/users/{userId}/config/{configDoc=**} {
                  allow read, write: if request.auth != null && request.auth.uid == userId; // Or admin access logic
                }
              }
            }
            ```

## Setup and Installation (End-to-End)

1.  **Prerequisites:**
    *   Google Cloud Platform account with billing enabled.
    *   Firebase project created and Firestore database enabled.
    *   Last.fm API Account: Register an API application on Last.fm to get an API Key and Shared Secret.
    *   ESP32 development board and RFID reader hardware.
    *   Node.js and `gcloud` CLI installed for Cloud Function deployment.
2.  **Firebase Setup:**
    *   In your Firebase project, enable Firestore.
    *   Note your Firebase project configuration for the Web UI.
3.  **ESP32 Setup:**
    *   Follow instructions in the "ESP32 CircuitPython Script" section above.
    *   Ensure `secrets.py` is configured with your Wi-Fi and MQTT broker details.
4.  **Cloud Function Deployment:**
    *   Navigate to the `cloud_function` directory.
    *   Set your `APP_ID` and `TARGET_USER_ID` values.
    *   Deploy using `gcloud functions deploy ...` as shown in the "Google Cloud Function" section. Ensure the Pub/Sub topic you specify here is the one your MQTT bridge will publish to.
5.  **Web UI Configuration:**
    *   Update `web_ui/js/firebase-config.js` with your Firebase project settings.
    *   Update `APP_ID` and `TARGET_USER_ID` in `web_ui/js/app.js`.
    *   Open `web_ui/index.html` in your browser or deploy it.
6.  **Last.fm Configuration (via Web UI):**
    *   Open the Web UI.
    *   Go to the "Last.fm Configuration" section.
    *   Enter your Last.fm API Key and API Secret. Click "Authenticate with Last.fm & Save Credentials".
    *   **Note:** The full Last.fm web authentication flow (redirect to Last.fm, callback handling, session key exchange) needs to be fully implemented in `web_ui/js/app.js` for scrobbling to work. This part is currently a placeholder.
7.  **Add Albums (via Web UI):**
    *   Use the "Album Management" section to associate your RFID tags with artists and albums.
8.  **Testing:** See "Testing and Integration" section in the original plan (or a separate TESTING.md).

## Usage

*   **ESP32:** Press the button connected to `BUTTON_PIN`. The ESP32 will attempt to scan an RFID tag and publish it. Check the serial monitor for logs.
*   **Web UI:**
    *   **Album Management:** Add new RFID tag/album mappings, edit existing ones, or delete them.
    *   **Log Viewing:** View logs generated by the Cloud Function (and potentially the ESP32 if it logged to a path the UI reads, though current setup logs via CF).
    *   **Last.fm Configuration:** Manage Last.fm API Key/Secret and (once fully implemented) the user session key.

## MQTT Bridge to Google Cloud Pub/Sub

The ESP32 script (`esp32_rfid_mqtt.py`) is configured to publish to a standard MQTT broker using username/password authentication. Google Cloud Pub/Sub, when used with an MQTT interface (like Google Cloud IoT Core), often expects JWT-based authentication from devices.

**You have a few options:**

1.  **Use Google Cloud IoT Core as the MQTT Broker:**
    *   Modify `esp32_rfid_mqtt.py` to handle JWT generation and connect to the Google Cloud IoT Core MQTT endpoint. This is more complex for CircuitPython.
    *   IoT Core can automatically bridge messages from its MQTT topics to Pub/Sub topics.
2.  **Use an Intermediate MQTT Broker and a Separate Bridge:**
    *   The ESP32 publishes to your chosen MQTT broker (e.g., Mosquitto, HiveMQ, or a cloud-based one).
    *   You set up a separate bridge application/service that subscribes to this MQTT topic and republishes messages to a Google Cloud Pub/Sub topic. This bridge could be a custom script, a service like VerneMQ's Pub/Sub bridge, etc.
    *   The Cloud Function trigger would then be this final Pub/Sub topic.
3.  **Direct ESP32 to Pub/Sub (More Advanced):** While less common for MQTT-native devices, explore if a CircuitPython library allows direct publishing to Pub/Sub with appropriate authentication, bypassing MQTT for the ESP32-to-cloud step.

**This project currently assumes the user will handle the MQTT message relay from the ESP32's target broker to the Google Cloud Pub/Sub topic that triggers the Cloud Function.**

## Troubleshooting

*   **ESP32 Issues:**
    *   Check `secrets.py` for correct Wi-Fi/MQTT credentials.
    *   Monitor serial output from ESP32 for error messages.
    *   Ensure all CircuitPython libraries are correctly installed in the `lib` folder.
*   **Cloud Function Errors:**
    *   Check logs in Google Cloud Logging for your function.
    *   Verify environment variables (`APP_ID`, `TARGET_USER_ID`) are set correctly.
    *   Ensure the service account has necessary IAM permissions.
*   **Scrobbles Not Appearing:**
    *   Verify Last.fm API Key, Secret, and Session Key are correctly stored in Firestore via the Web UI.
    *   Check Cloud Function logs for errors during Last.fm API calls.
    *   Ensure `TARGET_USER_ID` is correctly set and matches the user whose credentials are in Firestore.
*   **Web UI Issues:**
    *   Ensure `firebase-config.js` is correct.
    *   Check browser developer console for JavaScript errors.
    *   Verify Firestore security rules allow access.

## Future Enhancements

*   Full implementation of the Last.fm Web Auth Flow in `web_ui/js/app.js`.
*   More robust error handling, status indicators (LEDs) and retries in the ESP32 script.
*   User authentication for the Web UI itself (e.g., using Firebase Authentication).
*   Support for different RFID reader types on ESP32 with dynamic library loading or selection.
*   A more dynamic way to configure `APP_ID` and `TARGET_USER_ID` in the Web UI.
*   Option for the ESP32 to directly publish to Google Cloud IoT Core MQTT using JWTs.

## License

This project is released under the MIT License. See the (to be created) `LICENSE` file for details.
(You would typically add a `LICENSE` file with the chosen license text, e.g., MIT).
