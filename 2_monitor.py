import json, uuid, requests, time, os
from datetime import datetime, timezone

SETTINGS_FILE = "/opt/smart-light-guard/settings.json"
DECONZ_HOST = "http://127.0.0.1:8080"

def load_settings():
    if not os.path.exists(SETTINGS_FILE): return None
    with open(SETTINGS_FILE, 'r') as f: return json.load(f)

def trigger_inactivity_alert(settings):
    unique_event_uuid = f"evt-{uuid.uuid4()}" 
    current_utc_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    payload_data = {
        "event_uuid": unique_event_uuid,
        "hub_id": settings["backend"]["hub_id"],
        "event_type": "inactivity_alert",
        "event_time": current_utc_time,
        "payload": {}
    }
    
    headers = {
        "Content-Type": "application/json",
        "X-Hub-Api-Key": settings["backend"]["api_key"]
    }
    
    url = f"{settings['backend']['base_url']}/alerts"
    
    print(f"🚨 INAKTIVITÄT ERKANNT! Sende Alarm (UUID: {unique_event_uuid})...")
    try:
        response = requests.post(url, json=payload_data, headers=headers, timeout=10)
        if response.status_code in [200, 201]:
            print("✅ Alarm erfolgreich vom Backend verarbeitet!")
            return True
        else:
            print(f"❌ Fehler vom Backend: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"⚠️ Verbindungsfehler zum Backend: {e}")
    return False

def get_latest_sensor_activity(api_key):
    try:
        r = requests.get(f"{DECONZ_HOST}/api/{api_key}/sensors", timeout=5)
        if r.status_code != 200: return None
        
        latest_time = None
        for sid, data in r.json().items():
            state = data.get("state", {})
            last_updated = state.get("lastupdated")
            if last_updated and last_updated != "none":
                # deCONZ liefert ISO 8601 UTC ohne Z (z.B. "2026-03-18T16:00:00")
                try:
                    dt = datetime.strptime(last_updated, "%Y-%m-%dT%H:%M:%S")
                    dt = dt.replace(tzinfo=timezone.utc)
                    if not latest_time or dt > latest_time:
                        latest_time = dt
                except: pass
        return latest_time
    except:
        return None

if __name__ == "__main__":
    print("Starte Smart Light Guard Überwachungs-Dienst...")
    alert_triggered = False

    while True:
        settings = load_settings()
        if not settings or not settings.get("deconz_api_key") or not settings["backend"].get("hub_id"):
            time.sleep(30)
            continue
            
        timeout_seconds = settings["alert_settings"]["timeout_seconds"]
        latest_activity = get_latest_sensor_activity(settings["deconz_api_key"])
        
        if latest_activity:
            time_since_activity = (datetime.now(timezone.utc) - latest_activity).total_seconds()
            print(f"Letzte Bewegung vor {int(time_since_activity)} Sekunden (Limit: {timeout_seconds}s)")
            
            if time_since_activity > timeout_seconds:
                if not alert_triggered:
                    success = trigger_inactivity_alert(settings)
                    if success:
                        alert_triggered = True
                        print("⏳ Gehe in Cooldown-Modus für 1 Stunde, um Spam zu vermeiden...")
                        time.sleep(30) # 1 Stunde Cooldown nach Alarm
            else:
                # Bewegung erkannt, Reset des Alarm-Status
                alert_triggered = False
                
        time.sleep(10) # Alle 10 Sekunden prüfen