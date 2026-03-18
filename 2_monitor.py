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

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f: return json.load(f)
        except: pass
    return {"last_activity": time.time(), "last_alert": 0}

def save_state(state):
    try:
        with open(STATE_FILE, "w") as f: json.dump(state, f)
    except: pass

def update_state_activity(reason="Unbekannt"):
    state = load_state()
    state["last_activity"] = time.time()
    save_state(state)
    logger.info(f"⚡ Aktivität gespeichert: {reason}")

def on_ws_message(ws, message):
    try:
        data = json.loads(message)
        if data.get("e") == "changed":
            update_state_activity(f"WebSocket Event ID {data.get('id')}")
    except: pass

def websocket_thread():
    while True:
        # Wir nutzen jetzt fest Port 8088, den wir im setup.sh gesetzt haben
        ws_url = "ws://127.0.0.1:8088"
        try:
            logger.info(f"🔗 Verbinde mit WebSocket auf {ws_url}...")
            ws = websocket.WebSocketApp(ws_url, on_message=on_ws_message)
            ws.run_forever(ping_interval=10)
        except Exception as e:
            logger.error(f"WebSocket-Fehler: {e}")
        time.sleep(5)

def trigger_alert(settings):
    event_uuid = f"evt-{uuid.uuid4()}"
    payload = {
        "event_uuid": event_uuid,
        "hub_id": settings["backend"]["hub_id"],
        "event_type": "inactivity_alert",
        "event_time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "payload": {}
    }
    headers = {"X-Hub-Api-Key": settings["backend"]["api_key"]}
    try:
        r = requests.post(f"{settings['backend']['base_url']}/alerts", json=payload, headers=headers, timeout=10)
        return r.status_code in [200, 201]
    except: return False

if __name__ == "__main__":
    logger.info("🚀 Monitor gestartet (WebSocket 8088 + Hybrid-Polling)")
    threading.Thread(target=websocket_thread, daemon=True).start()
    
    while True:
        settings = load_settings()
        if not settings or not settings["backend"].get("hub_id"):
            time.sleep(30); continue
            
        timeout_seconds = settings["alert_settings"]["timeout_seconds"]
        state = load_state()
        now = time.time()
        
        # Inaktivitäts-Prüfung mit Smart Cooldown (1h)
        if state["last_activity"] > state["last_alert"]:
            if (now - state["last_activity"]) > timeout_seconds:
                if trigger_alert(settings):
                    state["last_alert"] = now
                    save_state(state)
                    logger.warning("🚨 Alarm gesendet! Starte 1h Cooldown.")
        elif (now - state["last_alert"]) > (3600 + timeout_seconds):
            if trigger_alert(settings):
                state["last_alert"] = now
                save_state(state)
        
        time.sleep(10)