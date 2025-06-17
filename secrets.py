# This file is where you keep secret settings, passwords, and tokens!
# If you put them in the code you risk committing them publicly.

secrets = {
    'ssid': 'YOUR_WIFI_SSID',
    'password': 'YOUR_WIFI_PASSWORD',
    'mqtt_broker': 'YOUR_MQTT_BROKER_ADDRESS',
    'mqtt_port': 1883, # Or 8883 for TLS
    'mqtt_username': 'YOUR_MQTT_USERNAME',
    'mqtt_password': 'YOUR_MQTT_PASSWORD',
    'mqtt_topic': 'esp32/rfid_tags',
    'aio_username': 'YOUR_AIO_USERNAME', # For Adafruit IO
    'aio_key': 'YOUR_AIO_KEY',          # For Adafruit IO
    # Add other secrets here as needed
}
