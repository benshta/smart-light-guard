import json, time, os, requests
from datetime import datetime, timezone
from slg_logger import get_logger

logger = get_logger("CLOUD-SYNC")
SETTINGS_FILE = "/opt/smart-light-guard/settings.json"
SYNC_INTERVAL = 600  # Alle 10 Minuten (passt besser zum Backend Check)

# HTTP Session für TCP-Keepalive und bessere Performance
session = requests.Session()

def send_heartbeat():
    if not os.path.exists(SETTINGS_FILE): return
    try:
        with open(SETTINGS_FILE, "r") as f: settings = json.load(f)
    except: return
    
    hub_id = settings["backend"].get("hub_id")
    api_key = settings["backend"].get("api_key")
    base_url = settings["backend"].get("base_url")

    if not hub_id or not api_key:
        return # Leise abbrechen, wenn noch nicht registriert

    headers = {"X-Hub-Api-Key": api_key, "Content-Type": "application/json"}
    payload = {
        "hub_id": hub_id,
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "version": "0.2.0" # Version angehoben
    }

    try:
        url = f"{base_url}/hubs/heartbeat"
        response = session.post(url, json=payload, headers=headers, timeout=10)
        
        if response.status_code in [200, 201]:
            logger.info("☁️ Heartbeat erfolgreich gesendet.")
            cloud_settings = response.json()
            if cloud_settings and "inactivity_threshold_hours" in cloud_settings:
                new_timeout = int(cloud_settings["inactivity_threshold_hours"]) * 3600
                if settings["alert_settings"]["timeout_seconds"] != new_timeout:
                    settings["alert_settings"]["timeout_seconds"] = new_timeout
                    with open(SETTINGS_FILE, "w") as f: json.dump(settings, f, indent=4)
                    logger.info(f"⚙️ Neue Timeouts vom Server übernommen: {new_timeout} Sekunden")
        else:
            logger.error(f"Heartbeat Fehler {response.status_code}: {response.text}")
    except requests.exceptions.RequestException as e:
        logger.warning(f"Netzwerkfehler beim Heartbeat (Backend offline?): {e}")

if __name__ == "__main__":
    logger.info("🚀 Starte Cloud Sync Agent...")
    while True:
        send_heartbeat()
        time.sleep(SYNC_INTERVAL)