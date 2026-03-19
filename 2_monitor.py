import json, uuid, requests, time, os, threading
import websocket
from datetime import datetime, timezone
from slg_logger import get_logger

logger = get_logger("MONITOR")
SETTINGS_FILE = "/opt/smart-light-guard/settings.json"
STATE_FILE = "/opt/smart-light-guard/state.json"
DECONZ_API = "http://127.0.0.1:8080/api"

# RAM CACHE - Verhindert das Zerstören der SD-Karte!
STATE_CACHE = {"last_activity": time.time(), "last_alert": 0}
LAST_DISK_SAVE = time.time()

def load_settings():
    if not os.path.exists(SETTINGS_FILE): return None
    try:
        with open(SETTINGS_FILE, 'r') as f: return json.load(f)
    except Exception as e:
        logger.error(f"Settings Fehler: {e}")
        return None

def load_state():
    global STATE_CACHE
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f: 
                disk_state = json.load(f)
                STATE_CACHE.update(disk_state)
        except: pass
    return STATE_CACHE

def save_state_to_disk(force=False):
    global STATE_CACHE, LAST_DISK_SAVE
    now = time.time()
    # Nur alle 15 Minuten speichern, es sei denn force=True (z.B. bei Alarm)
    if force or (now - LAST_DISK_SAVE) > 900:
        try:
            with open(STATE_FILE, "w") as f: json.dump(STATE_CACHE, f)
            LAST_DISK_SAVE = now
        except Exception as e:
            logger.error(f"Fehler beim Speichern des Status: {e}")

def update_state_activity(reason="Unbekannt"):
    global STATE_CACHE
    STATE_CACHE["last_activity"] = time.time()
    # Wir loggen es nur, schreiben es aber NICHT direkt auf die SD-Karte!
    logger.info(f"⚡ Aktivität erfasst im RAM: {reason}")

def on_ws_message(ws, message):
    try:
        data = json.loads(message)
        if data.get("e") == "changed":
            update_state_activity(f"WS Event ID {data.get('id')}")
    except: pass

def on_ws_error(ws, error):
    logger.warning(f"WebSocket Fehler: {error}")

def on_ws_close(ws, close_status_code, close_msg):
    logger.warning("WebSocket Verbindung geschlossen.")

def websocket_thread():
    ws_url = "ws://127.0.0.1:8088"
    while True:
        try:
            logger.info(f"🔗 Verbinde mit WebSocket auf {ws_url}...")
            ws = websocket.WebSocketApp(
                ws_url, 
                on_message=on_ws_message,
                on_error=on_ws_error,
                on_close=on_ws_close
            )
            ws.run_forever(ping_interval=10, ping_timeout=5)
        except Exception as e:
            logger.error(f"WebSocket-Absturz: {e}")
        
        logger.info("Warte 5s vor Reconnect...")
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
        r.raise_for_status()
        logger.info("✅ Alarm erfolgreich ans Backend gesendet!")
        return True
    except requests.exceptions.HTTPError as err:
        logger.error(f"🚨 Alarm vom Backend abgelehnt: {err.response.status_code} - {err.response.text}")
    except Exception as e:
        logger.error(f"🚨 Netzwerkfehler beim Alarm-Senden: {e}")
    return False

if __name__ == "__main__":
    logger.info("🚀 Monitor gestartet (RAM-Cache Modus + WS Reconnect)")
    load_state() # Initialer Ladevorgang
    threading.Thread(target=websocket_thread, daemon=True).start()
    
    while True:
        settings = load_settings()
        if not settings or not settings["backend"].get("hub_id"):
            time.sleep(30)
            continue
            
        timeout_seconds = settings["alert_settings"]["timeout_seconds"]
        now = time.time()
        
        # Inaktivitäts-Prüfung
        if STATE_CACHE["last_activity"] > STATE_CACHE["last_alert"]:
            if (now - STATE_CACHE["last_activity"]) > timeout_seconds:
                logger.warning(f"⏳ Timeout überschritten ({timeout_seconds}s). Sende Alarm...")
                if trigger_alert(settings):
                    STATE_CACHE["last_alert"] = now
                    save_state_to_disk(force=True) # Bei Alarm sofort auf Disk sichern!
                    logger.warning("🚨 Alarm gesendet! Starte 1h Cooldown.")
        elif (now - STATE_CACHE["last_alert"]) > (3600 + timeout_seconds):
            if trigger_alert(settings):
                STATE_CACHE["last_alert"] = now
                save_state_to_disk(force=True)
        
        # RAM-Cache zyklisch auf Disk sichern
        save_state_to_disk(force=False)
        time.sleep(10)