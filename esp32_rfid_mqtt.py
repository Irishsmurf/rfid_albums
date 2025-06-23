# SPDX-FileCopyrightText: 2024 User for Adafruit Industries
#
# SPDX-License-Identifier: MIT

# This script reads RFID tags using a serial reader connected to an ESP32
# running CircuitPython. It then publishes the scanned RFID tag ID to an
# MQTT broker.
#
# Dependencies:
# - settings.toml: Must be present in the root of CIRCUITPY drive with WiFi/MQTT credentials.
# - adafruit_minimqtt: Ensure this library and its dependencies are in the /lib folder.
#
# Setup:
# 1. Configure WiFi and MQTT details in 'settings.toml'.
# 2. Wire your serial RFID reader to the ESP32's UART pins (see UART setup below).
# 3. Copy this file as 'code.py' (or 'main.py') to your CIRCUITPY drive.

import time
import os
import board
import busio
import wifi
import socketpool
import adafruit_minimqtt.adafruit_minimqtt as MQTT
import microcontroller

# --- Configuration (from settings.toml) ---
WIFI_SSID = os.getenv("CIRCUITPY_WIFI_SSID")
WIFI_PASSWORD = os.getenv("CIRCUITPY_WIFI_PASSWORD")
MQTT_BROKER = os.getenv("MQTT_BROKER")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883)) # Default to 1883 if not set
MQTT_TOPIC = os.getenv("MQTT_TOPIC")
MQTT_USERNAME = os.getenv("MQTT_USERNAME")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")
MQTT_CLIENT_ID = f"esp32-rfid-{int(time.monotonic())}" # Unique client ID

# RFID Reader Serial Configuration
RFID_BAUD_RATE = 9600 # Common baud rate for serial RFID readers

# Attempt to get pins from settings.toml, otherwise use board defaults or common alternatives
# NOTE: board.TX and board.RX are often connected to USB serial.
# You might need to use a different UART peripheral if your reader is on other pins.
# For example, on some ESP32s, UART1 might be on board.IO17 (TX1) and board.IO16 (RX1).
# Consult your ESP32 board's pinout.
RFID_RX_PIN_NAME = os.getenv("RFID_RX_PIN")
RFID_TX_PIN_NAME = os.getenv("RFID_TX_PIN")

uart = None

def setup_uart():
    """Initialize UART for RFID reader."""
    global uart
    try:
        if RFID_RX_PIN_NAME and RFID_TX_PIN_NAME:
            rx_pin = getattr(board, RFID_RX_PIN_NAME)
            tx_pin = getattr(board, RFID_TX_PIN_NAME)
            print(f"Using UART pins from settings.toml: TX={RFID_TX_PIN_NAME}, RX={RFID_RX_PIN_NAME}")
        elif hasattr(board, "IO16") and hasattr(board, "IO17"): # Common alternative for ESP32 UART1
            rx_pin = board.IO16
            tx_pin = board.IO17
            print("Using UART pins: TX=IO17, RX=IO16 (Common for ESP32 UART1)")
        else: # Default to board.RX and board.TX if specific ones aren't found
            rx_pin = board.RX
            tx_pin = board.TX
            print(f"Using default UART pins: TX, RX. These might be REPL pins.")

        # Note: If your reader only sends data (TX pin on reader to RX pin on ESP32),
        # the tx_pin for the ESP32 UART might not be strictly necessary to define if not used.
        uart = busio.UART(tx_pin, rx_pin, baudrate=RFID_BAUD_RATE, timeout=0.1)
        print(f"UART initialized for RFID reader on RX:{rx_pin}, TX:{tx_pin} at {RFID_BAUD_RATE} baud.")
        return True
    except AttributeError as e:
        print(f"Error: Could not find specified UART pins. {e}")
        print("Please check your board pinout and settings.toml if using RFID_RX_PIN/RFID_TX_PIN.")
        print("Ensure the pin names (e.g., 'IO16') are correct attributes of the 'board' module.")
    except RuntimeError as e:
        print(f"Error: UART pins might already be in use (e.g., by REPL). {e}")
        print("Consider using a different UART peripheral or disabling REPL on these pins.")
    except Exception as e:
        print(f"Failed to initialize UART: {e}")
    return False

# --- WiFi Connection ---
def connect_wifi():
    """Connects to WiFi using credentials from settings.toml."""
    if wifi.radio.ipv4_address:
        print(f"Already connected to {WIFI_SSID}")
        return
    print(f"Connecting to WiFi SSID: {WIFI_SSID}...")
    try:
        wifi.radio.connect(WIFI_SSID, WIFI_PASSWORD)
        print(f"Connected to WiFi! IP Address: {wifi.radio.ipv4_address}")
    except ConnectionError as e:
        print(f"Failed to connect to WiFi: {e}")
        print("Retrying in 10 seconds...")
        time.sleep(10)
        connect_wifi() # Recursive call, consider max retries in a real app
    except Exception as e:
        print(f"An unexpected error occurred during WiFi connection: {e}")
        print("Retrying in 10 seconds...")
        time.sleep(10)
        connect_wifi()

# --- MQTT Setup ---
mqtt_client = None
pool = None

def connect_mqtt():
    """Connects to the MQTT broker."""
    global mqtt_client, pool
    if mqtt_client and mqtt_client.is_connected():
        return

    print(f"Attempting to connect to MQTT broker: {MQTT_BROKER}:{MQTT_PORT}")
    try:
        pool = socketpool.SocketPool(wifi.radio)
        mqtt_client = MQTT.MQTT(
            broker=MQTT_BROKER,
            port=MQTT_PORT,
            username=MQTT_USERNAME,
            password=MQTT_PASSWORD,
            socket_pool=pool,
            ssl_context=None, # No SSL for port 1883
            client_id=MQTT_CLIENT_ID,
            keep_alive=60
        )

        # Optional: Setup Last Will and Testament (LWT)
        # mqtt_client.will_set(topic=f"{MQTT_TOPIC}/status", payload="offline", qos=1, retain=True)

        print("Connecting to MQTT broker...")
        mqtt_client.connect()
        # mqtt_client.publish(f"{MQTT_TOPIC}/status", "online", qos=1, retain=True) # Announce online status
        print(f"Connected to MQTT broker: {MQTT_BROKER}")
    except MQTT.MMQTTException as e:
        print(f"MQTT Error: {e}")
        print("Retrying MQTT connection in 10 seconds...")
        time.sleep(10)
    except ConnectionRefusedError as e:
        print(f"MQTT Connection Refused: {e}. Check broker address, port, and credentials.")
        print("Retrying MQTT connection in 10 seconds...")
        time.sleep(10)
    except OSError as e:
        print(f"Network/Socket Error during MQTT connection: {e}")
        print("Retrying MQTT connection in 10 seconds...")
        time.sleep(10)
    except Exception as e:
        print(f"Failed to connect to MQTT: {e}")
        print("Retrying MQTT connection in 10 seconds...")
        time.sleep(10)
        # In a real app, avoid deep recursion on continuous failure.
        # Consider a reset or limited retries.

# --- Main Loop ---
def main():
    global uart, mqtt_client

    if not WIFI_SSID or not WIFI_PASSWORD:
        print("ERROR: WiFi SSID or Password not set in settings.toml. Halting.")
        return

    if not MQTT_BROKER or not MQTT_TOPIC or not MQTT_USERNAME or not MQTT_PASSWORD:
        print("ERROR: MQTT configuration missing in settings.toml. Halting.")
        return

    if not setup_uart():
        print("ERROR: Failed to initialize UART for RFID. Halting.")
        # Optionally, you could try to re-initialize or allow operation without UART
        # For now, we halt if UART setup fails.
        return

    last_tag_id = None
    last_tag_time = 0
    debounce_interval = 3 # seconds, to prevent rapid re-scans of the same tag

    while True:
        try:
            # Ensure WiFi is connected
            if not wifi.radio.ipv4_address:
                connect_wifi()
                if not wifi.radio.ipv4_address: # Still not connected after attempt
                    print("WiFi connection failed. Retrying in 30s.")
                    time.sleep(30)
                    continue # Skip to next loop iteration

            # Ensure MQTT is connected
            if mqtt_client is None or not mqtt_client.is_connected():
                connect_mqtt()
                if mqtt_client is None or not mqtt_client.is_connected(): # Still not connected
                    print("MQTT connection failed. Retrying in 10s.")
                    time.sleep(10)
                    continue # Skip to next loop iteration

            # Maintain MQTT connection
            mqtt_client.loop(timeout=0.1) # Non-blocking check for messages, ping

            if uart:
                # Read data from UART
                raw_data = uart.readline()
                if raw_data:
                    try:
                        tag_id = raw_data.decode('utf-8').strip()
                        if tag_id: # Ensure tag_id is not empty
                            current_time = time.monotonic()
                            if tag_id == last_tag_id and (current_time - last_tag_time) < debounce_interval:
                                print(f"Debounced duplicate scan: {tag_id}")
                            else:
                                print(f"--- Tag Scanned: {tag_id} ---")
                                last_tag_id = tag_id
                                last_tag_time = current_time

                                print(f"Publishing to {MQTT_TOPIC}: {tag_id}")
                                try:
                                    mqtt_client.publish(MQTT_TOPIC, tag_id, qos=1)
                                    print("Successfully published to MQTT.")
                                except MQTT.MMQTTException as e:
                                    print(f"MQTT Publish Error: {e}. Reconnecting...")
                                    # Attempt to reconnect if publish fails
                                    mqtt_client.disconnect() # Clean disconnect
                                    time.sleep(1)
                                    mqtt_client = None # Force re-init in next loop
                                except Exception as e:
                                    print(f"Generic error during MQTT publish: {e}")
                                    # Consider more specific error handling or reset

                        # Clear buffer if there's more data to prevent old reads
                        while uart.in_waiting > 0:
                            uart.read(uart.in_waiting)

                    except UnicodeDecodeError:
                        print("Warning: Received non-UTF-8 data from serial. Ignoring.")
                    except Exception as e:
                        print(f"Error processing RFID data: {e}")
            else:
                print("UART not available. Cannot read RFID tags.")
                time.sleep(5) # Wait before retrying or re-checking UART

        except ConnectionError as e: # Covers WiFi/Socket related issues broadly
            print(f"Connection error in main loop: {e}")
            if mqtt_client:
                try:
                    mqtt_client.disconnect()
                except:
                    pass # Ignore errors on disconnect
            mqtt_client = None
            # wifi.radio.connect might have been interrupted, try to reconnect implicitly
            time.sleep(10)
        except MQTT.MMQTTException as e:
            print(f"MQTT Exception in main loop: {e}")
            if mqtt_client:
                try:
                    mqtt_client.disconnect() # Attempt a clean disconnect
                except:
                    pass # Ignore errors on disconnect
            mqtt_client = None # Force re-initialization
            print("Attempting to re-establish MQTT connection...")
            time.sleep(5)
        except RuntimeError as e:
            print(f"RuntimeError in main loop: {e}")
            print("This might be a more critical error. Resetting microcontroller in 15s...")
            time.sleep(15)
            microcontroller.reset()
        except Exception as e:
            print(f"An unexpected error occurred in the main loop: {e}")
            print("Attempting to recover in 10 seconds...")
            time.sleep(10)

if __name__ == "__main__":
    main()
