import json, uuid, requests, time, os, threading
import websocket
from datetime import datetime, timezone
from slg_logger import get_logger

logger = get_logger("MONITOR")
SETTINGS_FILE = "/opt/smart-light-guard/settings.json"
STATE_FILE = "/opt/smart-light-guard/state.json"
DECONZ_API = "http://127.0.0.1:8080/api"

def load_settings():
    if not os.path.exists(SETTINGS_FILE): return None
    try:
        with open(SETTINGS_FILE, 'r') as f: return json.load(f)
    except: return None

def get_websocket_port(api_key):
    try:
        r = requests.get(f"{DECONZ_API}/{api_key}/config", timeout=5)
        return r.json().get("websocketport", 8080)
    except: return 8080

def update_state_activity():
    """Speichert den Zeitstempel der letzten Bewegung persistent."""
    now = time.time()
    try:
        with open(STATE_FILE, "w") as f: json.dump({"last_activity": now}, f)
    except Exception as e:
        logger.error(f"Konnte State nicht speichern: {e}")
    return now

def get_last_activity():
    """Liest den letzten Zeitstempel aus (überlebt Neustarts)."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f: 
                return json.load(f).get("last_activity", time.time())
        except: pass
    return update_state_activity()

def on_ws_message(ws, message):
    """Wird in der Millisekunde ausgelöst, in der ein Sensor funkt!"""
    try:
        data = json.loads(message)
        if data.get("e") == "changed" and "state" in data:
            state = data["state"]
            if "presence" in state or "buttonevent" in state or "open" in state:
                dev_type = data.get("r", "Sensor")
                dev_id = data.get("id", "?")
                logger.info(f"⚡ Aktivität in Echtzeit erkannt! ({dev_type} ID: {dev_id})")
                update_state_activity()
    except Exception as e:
        logger.error(f"WebSocket Parsing Fehler: {e}")

def websocket_thread():
    """Läuft im Hintergrund und lauscht permanent auf den Funkkanal."""
    settings = load_settings()
    while not settings or not settings.get("deconz_api_key"):
        time.sleep(10)
        settings = load_settings()
        
    ws_port = get_websocket_port(settings["deconz_api_key"])
    ws_url = f"ws://127.0.0.1:{ws_port}"
    logger.info(f"🔗 Verbinde mit deCONZ WebSocket auf {ws_url}...")
    
    while True:
        try:
            ws = websocket.WebSocketApp(ws_url, on_message=on_ws_message)
            ws.run_forever()
        except Exception as e:
            logger.error(f"WebSocket Absturz: {e}")
        logger.warning("WebSocket getrennt. Versuche Neustart in 5s...")
        time.sleep(5)

def trigger_alert(settings):
    event_uuid = f"evt-{uuid.uuid4()}" 
    current_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    payload = {
        "event_uuid": event_uuid, 
        "hub_id": settings["backend"]["hub_id"],
        "event_type": "inactivity_alert", 
        "event_time": current_utc, 
        "payload": {}
    }
    headers = {"Content-Type": "application/json", "X-Hub-Api-Key": settings["backend"]["api_key"]}
    url = f"{settings['backend']['base_url']}/alerts"
    
    logger.warning(f"🚨 INAKTIVITÄT ERKANNT! Sende Alarm (UUID: {event_uuid})...")
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        if r.status_code in [200, 201]:
            logger.info("✅ Alarm erfolgreich vom Backend verarbeitet!")
            return True
        logger.error(f"❌ Backend lehnte ab: {r.status_code} - {r.text}")
    except Exception as e:
        logger.error(f"⚠️ Cloud-Verbindungsfehler beim Alarm: {e}")
    return False

if __name__ == "__main__":
    logger.info("🚀 Starte Monitor (Echtzeit-Event-Architektur)...")
    
    # WebSocket-Lauscher als Hintergrund-Thread starten
    threading.Thread(target=websocket_thread, daemon=True).start()
    
    alert_triggered = False
    
    # Haupt-Thread: Überwacht stur den Timer
    while True:
        settings = load_settings()
        if not settings or not settings["backend"].get("hub_id"):
            time.sleep(30)
            continue
            
        timeout_seconds = settings["alert_settings"]["timeout_seconds"]
        last_activity = get_last_activity()
        time_since = time.time() - last_activity
        
        if time_since > timeout_seconds:
            if not alert_triggered:
                if trigger_alert(settings):
                    alert_triggered = True
                    logger.info("⏳ Gehe in Cooldown (1 Stunde), um Spam zu vermeiden...")
                    time.sleep(30)
        else:
            if alert_triggered:
                logger.info("🟢 Bewegung erkannt! Alarm-Status zurückgesetzt. System wieder scharf.")
                alert_triggered = False
                
        time.sleep(10)