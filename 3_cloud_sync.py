import json, time, os, requests
from datetime import datetime, timezone

SETTINGS_FILE = "/opt/smart-light-guard/settings.json"
HEARTBEAT_URL = "https://eldercare.palffy.top/api/v1/hubs/heartbeat"
SYNC_INTERVAL = 900  # 15 Minuten

def send_heartbeat():
    if not os.path.exists(SETTINGS_FILE): return
    with open(SETTINGS_FILE, "r") as f: settings = json.load(f)
    
    hub_id = settings.get("hub_id")
    api_key = settings.get("hub_api_key")

    if not hub_id or not api_key:
        print("Kein Hub registriert. Überspringe Heartbeat.")
        return

    headers = {"X-Hub-Api-Key": api_key, "Content-Type": "application/json"}
    payload = {
        "hub_id": hub_id,
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "version": "0.1.0"
    }

    try:
        response = requests.post(HEARTBEAT_URL, json=payload, headers=headers, timeout=10)
        if response.status_code == 200:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Heartbeat gesendet.")
            
            # Neue Settings vom Server verarbeiten (falls vorhanden)
            cloud_settings = response.json()
            if cloud_settings and cloud_settings.get("inactivity_threshold_hours"):
                # Wenn der Server die Stunden schickt, rechnen wir sie in Sekunden um
                settings["timeout_seconds"] = int(cloud_settings["inactivity_threshold_hours"]) * 3600
                with open(SETTINGS_FILE, "w") as f: json.dump(settings, f, indent=4)
                print("Neue Timeouts vom Server übernommen!")
    except Exception as e:
        print(f"Cloud-Fehler: {e}")

if __name__ == "__main__":
    print("Starte Cloud Sync Agent...")
    while True:
        send_heartbeat()
        time.sleep(SYNC_INTERVAL)