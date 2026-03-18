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

# --- NEUES STATE-MANAGEMENT ---
def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f: return json.load(f)
        except: pass
    return {"last_activity": time.time(), "last_alert": 0}

def save_state(state):
    try:
        with open(STATE_FILE, "w") as f: json.dump(state, f)
    except Exception as e:
        logger.error(f"Konnte State nicht speichern: {e}")

def update_state_activity():
    """Wird bei jeder erkannten Aktivität (Bewegung, Licht an) aufgerufen."""
    state = load_state()
    state["last_activity"] = time.time()
    save_state(state)
    return state["last_activity"]

def set_alert_triggered():
    """Speichert den Zeitpunkt des Alarms ab."""
    state = load_state()
    state["last_alert"] = time.time()
    save_state(state)
# ------------------------------

def on_ws_message(ws, message):
    """Wird in der Millisekunde ausgelöst, in der ein Gerät funkt!"""
    try:
        data = json.loads(message)
        if data.get("e") == "changed" and "state" in data:
            state = data["state"]
            
            is_activity = False
            activity_type = "Unbekannt"
            
            if "presence" in state and state["presence"] == True:
                is_activity = True; activity_type = "Bewegung"
            elif "open" in state:
                is_activity = True; activity_type = "Tür/Fenster"
            elif "buttonevent" in state:
                is_activity = True; activity_type = "Knopfdruck"
            elif "on" in state:
                is_activity = True; activity_type = "Licht geschaltet"

            if is_activity:
                dev_type = data.get("r", "Gerät") 
                dev_id = data.get("id", "?")
                logger.info(f"⚡ Aktivität [{activity_type}] erkannt! ({dev_type} ID: {dev_id})")
                
                # Wenn eine Bewegung stattfindet, wird der Timer sicher resettet
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
    logger.info("🚀 Starte Monitor (Smart Cooldown Architektur)...")
    
    threading.Thread(target=websocket_thread, daemon=True).start()
    
    # Haupt-Thread: Überwacht stur die Limits ohne den Thread zu blockieren
    while True:
        settings = load_settings()
        if not settings or not settings["backend"].get("hub_id"):
            time.sleep(30)
            continue
            
        timeout_seconds = settings["alert_settings"]["timeout_seconds"]
        state = load_state()
        now = time.time()
        
        last_activity = state.get("last_activity", now)
        last_alert = state.get("last_alert", 0)
        
        # 1. GAB ES EINE BEWEGUNG SEIT DEM LETZTEN ALARM?
        if last_activity > last_alert:
            # Normaler Modus
            time_since_activity = now - last_activity
            if time_since_activity > timeout_seconds:
                if trigger_alert(settings):
                    set_alert_triggered()
                    logger.info("⏳ Gehe in Cooldown (1 Stunde)...")
        
        # 2. ES GAB KEINE BEWEGUNG SEIT DEM ALARM
        else:
            time_since_alert = now - last_alert
            cooldown_seconds = 3600 # 1 Stunde Pause
            
            if time_since_alert > cooldown_seconds:
                # Cooldown ist abgelaufen. Wir warten jetzt WIEDER timeout_seconds (X Stunden/Minuten).
                time_since_cooldown_end = time_since_alert - cooldown_seconds
                if time_since_cooldown_end > timeout_seconds:
                    logger.warning("Erneute Inaktivität nach Cooldown erkannt! Nächster Alarm wird gesendet.")
                    if trigger_alert(settings):
                        set_alert_triggered()
                        logger.info("⏳ Gehe erneut in Cooldown (1 Stunde)...")
                        
        time.sleep(10) # 10 Sekunden warten und Timer neu prüfen