import serial
import time
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

# 3. Serial Port for RFID Reader
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
    while True:
        try:
            print(f"Attempting to connect to RFID reader on {SERIAL_PORT}...")
            with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1) as ser:
                print(f"Successfully connected to reader. Waiting for scans...")
                while True:
                    line = ser.readline()
                    if line:
                        # Decode from bytes, strip whitespace/newlines
                        tag_id = line.decode('utf-8').strip()
                        if tag_id:
                            print(f"--- Tag Scanned: {tag_id} ---")
                            
                            # The collection path must match the web app's listener
                            scans_collection_ref = db.collection(f'artifacts/{APP_ID}/public/data/scans')
                            
                            scan_data = {
                                'rfid': tag_id,
                                'scannedAt': firestore.SERVER_TIMESTAMP
                            }
                            
                            # Add a new document to the 'scans' collection
                            update_time, doc_ref = scans_collection_ref.add(scan_data)
                            print(f"Successfully sent tag ID to Firebase (Doc ID: {doc_ref.id})")

        except serial.SerialException as e:
            print(f"Error: Could not open serial port {SERIAL_PORT}.")
            print("Please check the port name and ensure the reader is connected.")
            print("Retrying in 10 seconds...")
            time.sleep(10)
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            print("Retrying in 10 seconds...")
            time.sleep(10)


if __name__ == '__main__':
    if APP_ID == 'default-scrobbler-app':
         print("WARNING: You are using the default App ID. Please update the APP_ID variable in the script.")
    listen_for_rfid_scans()

