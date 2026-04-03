import json
import time
import requests
import argparse
from logger import get_logger

logger = get_logger("PAIRING")
SETTINGS_FILE = "/opt/smart-light-guard/settings.json"

def get_api_key():
    try:
        with open(SETTINGS_FILE, "r") as f:
            settings = json.load(f)
            return settings.get("deconz_api_key")
    except Exception as e:
        logger.error(f"Fehler beim Lesen der settings.json: {e}")
        return None

def trigger_pairing():
    api_key = get_api_key()
    if not api_key:
        logger.error("Kein deCONZ API-Key in settings.json gefunden. Pairing abgebrochen.")
        return False
        
    url = f"http://127.0.0.1:8080/api/{api_key}/config"
    payload = {"permitjoin": 60}
    
    try:
        response = requests.put(url, json=payload, timeout=5)
        if response.status_code == 200:
            logger.info("✅ Pairing-Modus für 60 Sekunden aktiviert.")
            print("Pairing-Modus für 60 Sekunden aktiviert.")
            return True
        else:
            logger.error(f"Fehler bei deCONZ API ({response.status_code}): {response.text}")
            print(f"Fehler: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Netzwerkfehler beim Pairing-Aufruf: {e}")
        print("Netzwerkfehler.")
        return False

def setup_gpio():
    try:
        import RPi.GPIO as GPIO
        GPIO.setmode(GPIO.BCM)
        BUTTON_PIN = 17
        GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        
        def button_callback(channel):
            logger.info("Physischer Pairing-Button gedrückt.")
            trigger_pairing()
            
        GPIO.add_event_detect(BUTTON_PIN, GPIO.FALLING, callback=button_callback, bouncetime=1500)
        logger.info(f"GPIO Listener auf Pin {BUTTON_PIN} gestartet (Warte auf Tastendruck).")
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            GPIO.cleanup()
            logger.info("GPIO Listener beendet.")
            
    except ImportError:
        logger.error("RPi.GPIO nicht gefunden (nur auf Raspberry Pi verfügbar).")
        print("Kann GPIO nicht starten, RPi.GPIO fehlt.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Smart Light Guard Pairing Tool")
    parser.add_argument('--listen', action='store_true', help='Starte GPIO Listener für physischen Button')
    args = parser.parse_args()
    
    if args.listen:
        setup_gpio()
    else:
        logger.info("Starte manuelles Pairing via CLI...")
        trigger_pairing()
