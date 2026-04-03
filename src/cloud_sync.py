import json, time, os, requests
from datetime import datetime, timezone
from logger import get_logger

logger = get_logger("CLOUD-SYNC")
SETTINGS_FILE = "/opt/smart-light-guard/settings.json"
SYNC_INTERVAL = 600  # Alle 10 Minuten (passt besser zum Backend Check)

# HTTP Session für TCP-Keepalive und bessere Performance
session = requests.Session()

def get_local_state(api_key):
    state = {
        "hardware_ok": False,
        "zigbee_devices": []
    }
    
    if os.path.exists("/dev/ttyAMA0") and os.access("/dev/ttyAMA0", os.W_OK | os.R_OK):
        state["hardware_ok"] = True
        
    if api_key:
        try:
            resp = requests.get(f"http://127.0.0.1:8080/api/{api_key}/sensors", timeout=5)
            if resp.status_code == 200:
                sensors = resp.json()
                for key, sensor in sensors.items():
                    if sensor.get("type", "") != "Daylight":
                        state["zigbee_devices"].append({
                            "id": key,
                            "name": sensor.get("name"),
                            "type": sensor.get("type"),
                            "uniqueid": sensor.get("uniqueid")
                        })
        except requests.exceptions.RequestException:
            pass
            
    return state

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
        "version": "0.3.0",
        "local_state": get_local_state(settings.get("deconz_api_key"))
    }

    try:
        url = f"{base_url}/hubs/heartbeat"
        response = session.post(url, json=payload, headers=headers, timeout=10)
        
        if response.status_code in [200, 201]:
            logger.info("☁️ Heartbeat erfolgreich gesendet.")
            cloud_settings = response.json()
            if cloud_settings:
                settings_changed = False
                
                if "inactivity_threshold_hours" in cloud_settings:
                    new_timeout = int(cloud_settings["inactivity_threshold_hours"]) * 3600
                    if settings.setdefault("alert_settings", {}).get("timeout_seconds") != new_timeout:
                        settings["alert_settings"]["timeout_seconds"] = new_timeout
                        settings_changed = True
                        logger.info(f"⚙️ Neue Timeouts vom Server übernommen: {new_timeout} Sekunden")
                
                if "tracked_wlan_devices" in cloud_settings:
                    if settings.get("tracked_wlan_devices") != cloud_settings["tracked_wlan_devices"]:
                        settings["tracked_wlan_devices"] = cloud_settings["tracked_wlan_devices"]
                        settings_changed = True
                        logger.info("⚙️ WLAN-Geräte Settings aktualisiert.")
                        
                if "zigbee_settings" in cloud_settings:
                    if settings.get("zigbee_settings") != cloud_settings["zigbee_settings"]:
                        settings["zigbee_settings"] = cloud_settings["zigbee_settings"]
                        settings_changed = True
                        logger.info("⚙️ Zigbee-Settings aktualisiert.")
                        
                if settings_changed:
                    with open(SETTINGS_FILE, "w") as f: json.dump(settings, f, indent=4)
        else:
            logger.error(f"Heartbeat Fehler {response.status_code}: {response.text}")
    except requests.exceptions.RequestException as e:
        logger.warning(f"Netzwerkfehler beim Heartbeat (Backend offline?): {e}")

if __name__ == "__main__":
    logger.info("🚀 Starte Cloud Sync Agent...")
    while True:
        send_heartbeat()
        time.sleep(SYNC_INTERVAL)