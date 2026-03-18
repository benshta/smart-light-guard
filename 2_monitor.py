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
    """Liest den Port dynamisch aus der deCONZ-Config aus."""
    try:
        r = requests.get(f"{DECONZ_API}/{api_key}/config", timeout=5)
        config = r.json()
        port = config.get("websocketport")
        if port:
            logger.info(f"✅ WebSocket-Port vom Gateway erkannt: {port}")
            return port
    except Exception as e:
        logger.error(f"Fehler beim Abrufen des WebSocket-Ports: {e}")
    return 8080 # Fallback auf deinen Port

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
    state = load_state()
    state["last_activity"] = time.time()
    save_state(state)
    return state["last_activity"]

def set_alert_triggered():
    state = load_state()
    state["last_alert"] = time.time()
    save_state(state)

def on_ws_message(ws, message):
    try:
        data = json.loads(message)
        if data.get("e") == "changed":
            state = data.get("state", {})
            config = data.get("config", {})
            dev_id = data.get("id", "?")
            dev_res = data.get("r", "Gerät")
            
            activity_detected = False
            reason = ""

            # FUNK-EVENTS (Digital)
            if state.get("presence") is True:
                activity_detected = True; reason = "Bewegung"
            elif "open" in state:
                activity_detected = True; reason = "Tür/Fenster Kontakt"
            elif "buttonevent" in state:
                activity_detected = True; reason = "Schalter gedrückt"
            elif "on" in state or "bri" in state:
                activity_detected = True; reason = "Licht-Status (Funk)"
            
            # PHYSISCHE EVENTS (Strom weg/an)
            # Prüft 'reachable' in state (Lichter) oder config (Sensoren)
            elif "reachable" in state or "reachable" in config:
                activity_detected = True
                is_reachable = state.get("reachable") if "reachable" in state else config.get("reachable")
                status = "Verbunden (AN)" if is_reachable else "Getrennt (AUS)"
                reason = f"Strom-Status: {status}"

            if activity_detected:
                logger.info(f"⚡ AKTIVITÄT: {reason} | ID: {dev_id} ({dev_res})")
                update_state_activity()
                
    except Exception as e:
        logger.error(f"Fehler im WebSocket-Parsing: {e}")

def websocket_thread():
    while True:
        settings = load_settings()
        if not settings or not settings.get("deconz_api_key"):
            time.sleep(10)
            continue
            
        api_key = settings["deconz_api_key"]
        ws_port = get_websocket_port(api_key)
        ws_url = f"ws://127.0.0.1:{ws_port}"
        
        logger.info(f"🔗 Verbinde mit WebSocket auf {ws_url}...")
        try:
            ws = websocket.WebSocketApp(ws_url, on_message=on_ws_message)
            ws.run_forever()
        except Exception as e:
            logger.error(f"WebSocket-Fehler: {e}")
        
        time.sleep(5)

def trigger_alert(settings):
    event_uuid = f"evt-{uuid.uuid4()}" 
    current_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    payload = {
        "event_uuid": event_uuid, "hub_id": settings["backend"]["hub_id"],
        "event_type": "inactivity_alert", "event_time": current_utc, "payload": {}
    }
    headers = {"Content-Type": "application/json", "X-Hub-Api-Key": settings["backend"]["api_key"]}
    url = f"{settings['backend']['base_url']}/alerts"
    
    logger.warning(f"🚨 ALARM! Sende Inaktivität (UUID: {event_uuid})...")
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        if r.status_code in [200, 201]:
            logger.info("✅ Cloud hat den Alarm bestätigt.")
            return True
    except Exception as e:
        logger.error(f"⚠️ Cloud-Fehler: {e}")
    return False

if __name__ == "__main__":
    logger.info("🚀 Monitor-Dienst gestartet.")
    threading.Thread(target=websocket_thread, daemon=True).start()
    
    while True:
        settings = load_settings()
        if not settings or not settings["backend"].get("hub_id"):
            time.sleep(30)
            continue
            
        timeout_seconds = settings["alert_settings"]["timeout_seconds"]
        state = load_state()
        now = time.time()
        
        last_act = state.get("last_activity", now)
        last_alr = state.get("last_alert", 0)
        
        if last_act > last_alr:
            # Warte auf Timeout
            if (now - last_act) > timeout_seconds:
                if trigger_alert(settings):
                    set_alert_triggered()
                    logger.info("⏳ Cooldown aktiv (1h)...")
        else:
            # Nach Alarm: 1h Pause, dann wieder X Sekunden warten
            time_since_alert = now - last_alr
            if time_since_alert > 3600:
                if time_since_alert > (3600 + timeout_seconds):
                    if trigger_alert(settings):
                        set_alert_triggered()
        
        time.sleep(10)