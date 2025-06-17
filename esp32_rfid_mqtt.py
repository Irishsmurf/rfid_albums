import time
import board
import digitalio
import alarm
import busio
import wifi
import socketpool
import adafruit_minimqtt.adafruit_minimqtt as MQTT

# Try to import secrets, if it fails, provide a message
try:
    from secrets import secrets
except ImportError:
    print("WiFi and MQTT secrets are kept in secrets.py, please add them there!")
    raise

# --- Configuration ---
BUTTON_PIN = board.IO0  # Example, adjust to actual button pin
RFID_RX_PIN = board.IO1 # ESP32 typical UART2 RX if using UART
RFID_TX_PIN = board.IO2 # ESP32 typical UART2 TX if using UART (TX not always needed for reader)
UART_BAUDRATE = 9600

# --- Global objects ---
button = digitalio.DigitalInOut(BUTTON_PIN)
button.switch_to_input(pull=digitalio.Pull.UP)

uart = None # Initialize later if RFID reader is UART based
pool = None
mqtt_client = None

# --- Wi-Fi Functions ---
def setup_wifi():
    global pool
    print("Connecting to WiFi...")
    try:
        wifi.radio.connect(secrets['ssid'], secrets['password'])
        pool = socketpool.SocketPool(wifi.radio)
        print(f"Connected to {secrets['ssid']}! IP: {wifi.radio.ipv4_address}")
        return True
    except Exception as e:
        print(f"Failed to connect to WiFi: {e}")
        return False

def disable_wifi():
    print("Disconnecting WiFi...")
    try:
        wifi.radio.enabled = False # Disconnect and disable radio
        print("WiFi disabled.")
    except Exception as e:
        print(f"Error disabling WiFi: {e}")

# --- MQTT Functions ---
def setup_mqtt_client():
    global mqtt_client
    print("Setting up MQTT client...")
    mqtt_client = MQTT.MQTT(
        broker=secrets['mqtt_broker'],
        port=secrets['mqtt_port'],
        username=secrets['mqtt_username'],
        password=secrets['mqtt_password'],
        socket_pool=pool,
        ssl_context=None, # Add SSL context if using TLS/SSL
    )
    # Setup MQTT event handlers
    mqtt_client.on_connect = mqtt_connected
    mqtt_client.on_disconnect = mqtt_disconnected
    mqtt_client.on_message = mqtt_message_received # Though this script primarily publishes

def connect_mqtt():
    if not mqtt_client:
        print("MQTT client not set up.")
        return False
    print(f"Connecting to MQTT broker {secrets['mqtt_broker']}...")
    try:
        mqtt_client.connect()
        return True
    except Exception as e:
        print(f"Failed to connect to MQTT broker: {e}")
        return False

def disconnect_mqtt():
    if mqtt_client and mqtt_client.is_connected():
        print("Disconnecting from MQTT broker...")
        try:
            mqtt_client.disconnect()
        except Exception as e:
            print(f"Error disconnecting MQTT: {e}")

def publish_to_mqtt(tag_id):
    if not mqtt_client or not mqtt_client.is_connected():
        print("MQTT client not connected. Cannot publish.")
        return False

    topic = secrets['mqtt_topic']
    payload = str(tag_id) # Ensure payload is string
    print(f"Publishing tag '{payload}' to topic '{topic}'...")
    try:
        mqtt_client.publish(topic, payload, qos=1) # Using QoS 1 for some reliability
        print("Published.")
        return True
    except Exception as e:
        print(f"Failed to publish to MQTT: {e}")
        return False

# MQTT Event Handlers
def mqtt_connected(client, userdata, flags, rc):
    print(f"Connected to MQTT! Flags: {flags} RC: {rc}")

def mqtt_disconnected(client, userdata, rc):
    print(f"Disconnected from MQTT. RC: {rc}")

def mqtt_message_received(client, topic, message):
    print(f"Received message on topic {topic}: {message}")


# --- RFID Function (UART based example) ---
def setup_rfid_reader():
    global uart
    print("Setting up UART for RFID reader...")
    try:
        # For ESP32, UART1 can be on any pins, UART0 is REPL, UART2 is also flexible
        # Adjust pins based on your ESP32 board and where you connect the reader
        uart = busio.UART(RFID_TX_PIN, RFID_RX_PIN, baudrate=UART_BAUDRATE, timeout=0.1)
        print("UART for RFID reader initialized.")
        return True
    except Exception as e:
        print(f"Error initializing UART for RFID: {e}")
        return False

def read_rfid_tag_uart():
    if not uart:
        print("UART for RFID not initialized.")
        return None

    print("Attempting to read RFID tag via UART...")
    try:
        # Simple UART readers might just send the tag ID followed by a newline
        data = uart.readline()
        if data:
            # Convert bytes to string and strip whitespace/newlines
            tag_id = data.decode('ascii').strip()
            if tag_id: # Ensure it's not an empty string after stripping
                print(f"RFID tag read: {tag_id}")
                return tag_id
            else:
                print("No RFID data or empty tag received.")
                return None
        else:
            #print("No data from UART.") # Can be spammy, enable for debugging
            return None
    except Exception as e:
        print(f"Error reading from UART RFID: {e}")
        return None

# --- Power Management ---
def go_to_sleep():
    print("Going to sleep until next button press...")
    # Deinitialize peripherals if necessary (MQTT is disconnected, WiFi disabled)
    if uart:
        uart.deinit()
        print("UART deinitialized.")

    pin_alarm = alarm.pin.PinAlarm(pin=BUTTON_PIN, value=False, pull=True)
    alarm.exit_and_deep_sleep_until_alarms(pin_alarm)

# --- Main Loop ---
wake_alarm = alarm.wake_alarm
if wake_alarm:
    print(f"Woke up from alarm: {wake_alarm}")
else:
    print("Woke up from power-on or reset.")

# Main execution block: run on pin alarm (button press) or initial power-on
if isinstance(wake_alarm, alarm.pin.PinAlarm) or wake_alarm is None:
    if wake_alarm is None:
        print("Initial boot sequence.")
    else:
        print("Button press detected.")

    rfid_tag = None
    if setup_rfid_reader(): # Initialize UART for RFID
        # Add a short delay or a loop to allow RFID reading attempts
        # For a real scenario, you might loop for a few seconds or until a tag is read
        for _ in range(5): # Try for ~0.5 seconds if UART timeout is 0.1s
            rfid_tag = read_rfid_tag_uart()
            if rfid_tag:
                break
            # time.sleep(0.1) # Small delay between reads if not handled by uart.timeout

    if rfid_tag:
        if setup_wifi():
            setup_mqtt_client() # Requires pool from setup_wifi()
            if connect_mqtt():
                publish_to_mqtt(rfid_tag)
                # Loop to process incoming MQTT messages for a short period if needed
                # For this use case, we mostly publish, but good to pump the loop a bit
                try:
                    mqtt_client.loop(timeout=1) # Process incoming messages, keepalive
                except Exception as e:
                    print(f"Error in MQTT loop: {e}")
                disconnect_mqtt()
            disable_wifi()
    else:
        print("No RFID tag read. Not proceeding with MQTT.")

    go_to_sleep()

else:
    print(f"Woke from an unexpected alarm ({type(wake_alarm)}). Going back to sleep.")
    go_to_sleep()
