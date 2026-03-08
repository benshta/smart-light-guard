import time
import json
import os
import requests

SETTINGS_FILE = "settings.json"
STATE_FILE = "state.json"

# Platzhalter-APIs für deine Cloud
CLOUD_HEALTH_API = "https://api.deine-domain.com/v1/health"
CLOUD_SETTINGS_API = "https://api.deine-domain.com/v1/settings/smart-light-guard-poc"

HEARTBEAT_INTERVAL = 300  # 5 Minuten
SYNC_INTERVAL = 900       # 15 Minuten

def load_local_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                return json.load(f)
        except: pass
    return {"updated_at": 0}

def save_local_settings(data):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f, indent=2)
    print("☁️ [SYNC] Lokale Settings aus der Cloud aktualisiert.")

def send_heartbeat():
    try:
        state = {}
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
                
        payload = {
            "device_id": "smart-light-guard-poc",
            "status": "online",
            "last_sensor_activity": state.get("last_activity", 0),
            "timestamp": time.time()
        }
        # requests.post(CLOUD_HEALTH_API, json=payload, timeout=5)
        print("💓 [HEALTH] Heartbeat an Cloud gesendet.")
    except Exception as e:
        print(f"⚠️ [HEALTH] Fehler: {e}")

def sync_settings():
    local_settings = load_local_settings()
    local_time = local_settings.get("updated_at", 0)
    
    try:
        # Mockup für POC:
        cloud_settings = {"updated_at": 0} 
        cloud_time = cloud_settings.get("updated_at", 0)
        
        if cloud_time > local_time:
            save_local_settings(cloud_settings)
        elif local_time > cloud_time:
            # requests.put(CLOUD_SETTINGS_API, json=local_settings, timeout=5)
            print("☁️ [SYNC] Lokale Änderungen in die Cloud gepusht.")
            
    except Exception as e:
        print(f"⚠️ [SYNC] Fehler: {e}")

if __name__ == "__main__":
    print("☁️ Cloud Sync Agent gestartet...")
    last_heartbeat = 0
    last_sync = 0
    
    while True:
        current_time = time.time()
        if current_time - last_heartbeat >= HEARTBEAT_INTERVAL:
            send_heartbeat()
            last_heartbeat = current_time
        if current_time - last_sync >= SYNC_INTERVAL:
            sync_settings()
            last_sync = current_time
        time.sleep(10)