import json, requests, os, uuid
from datetime import datetime, timezone

SETTINGS_FILE = "/opt/smart-light-guard/settings.json"
ALERT_URL = "https://eldercare.palffy.top/api/v1/alerts"

def fire_alarm():
    if not os.path.exists(SETTINGS_FILE):
        print("Settings fehlen. Kann keinen Alarm senden.")
        return

    with open(SETTINGS_FILE, "r") as f:
        settings = json.load(f)
        
    hub_id = settings.get("hub_id")
    api_key = settings.get("hub_api_key")

    if not hub_id or not api_key:
        print("Gerät ist nicht registriert! Alarm wird lokal verworfen.")
        return

    headers = {
        "X-Hub-Api-Key": api_key,
        "Content-Type": "application/json"
    }
    
    # Payload exakt nach deiner Swagger Spezifikation
    payload = {
        "event_uuid": str(uuid.uuid4()),
        "hub_id": hub_id,
        "event_type": "inactivity_alert",
        "event_time": datetime.now(timezone.utc).isoformat(),
        "payload": {}
    }

    try:
        print("Sende Alarm an Cloud-Backend...")
        response = requests.post(ALERT_URL, json=payload, headers=headers, timeout=10)
        if response.status_code == 200:
            print("✅ Alarm erfolgreich beim Backend registriert!")
        else:
            print(f"❌ Backend lehnte Alarm ab. Code: {response.status_code}, Fehler: {response.text}")
    except Exception as e:
        print(f"❌ Verbindungsfehler beim Alarm-Senden: {e}")

if __name__ == "__main__":
    fire_alarm()