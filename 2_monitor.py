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
    """Wird bei JEDEM Lebenszeichen aufgerufen (Funk, Sensor, Physischer Schalter)."""
    state = load_state()
    state["last_activity"] = time.time()
    save_state(state)
    return state["last_activity"]

def set_alert_triggered():
    """Speichert den Zeitpunkt des Alarms für die Cooldown-Berechnung."""
    state = load_state()
    state["last_alert"] = time.time()
    save_state(state)

def on_ws_message(ws, message):
    """
    Diese Funktion ist das Herzstück. Sie erkennt:
    1. Funk-Events (Bewegung, Licht an via App, Knopfdruck)
    2. Physische Events (Strom weg via Wandschalter = reachable: false)
    """
    try:
        data = json.loads(message)
        if data.get("e") == "changed":
            state = data.get("state", {})
            config = data.get("config", {})
            dev_id = data.get("id", "?")
            dev_res = data.get("r", "Gerät") # 'sensors' oder 'lights'
            
            activity_detected = False
            reason = ""

            # --- FALL A: FUNK-AKTIVITÄT ---
            # Bewegungsmelder schlägt an
            if state.get("presence") is True:
                activity_detected = True; reason = "Bewegung erkannt"
            # Tür/Fenster wird bewegt
            elif "open" in state:
                activity_detected = True; reason = "Tür/Fenster Kontakt"
            # Schalter wurde physisch gedrückt (Funk-Signal)
            elif "buttonevent" in state:
                activity_detected = True; reason = "Schalter gedrückt"
            # Licht wurde via App/Funk geschaltet oder gedimmt
            elif "on" in state or "bri" in state:
                activity_detected = True; reason = "Licht-Status geändert (Funk)"

            # --- FALL B: PHYSISCHE AKTIVITÄT (Stromschalter) ---
            # Wenn die Lampe vom Strom geht oder wiederkommt, ändert sich 'reachable'
            # (Wichtig: 'reachable' kann im 'state' oder in der 'config' stecken)
            elif "reachable" in state or "reachable" in config:
                activity_detected = True
                is_reachable = state.get("reachable") if "reachable" in state else config.get("reachable")
                status = "Verbunden (Strom AN)" if is_reachable else "Getrennt (Strom AUS)"
                reason = f"Physischer Netz-Status: {status}"

            if activity_detected:
                logger.info(f"⚡ AKTIVITÄT: {reason} | ID: {dev_id} ({dev_res})")
                update_state_activity()
                
    except Exception as e:
        logger.error(f"Fehler beim Verarbeiten des WebSocket-Events: {e}")

def websocket_thread():
    """Hintergrund-Thread, der permanent auf Funk-Signale lauscht."""
    settings = load_settings()
    while not settings or not settings.get("deconz_api_key"):
        time.sleep(10)
        settings = load_settings()
        
    ws_port = get_websocket_port(settings["deconz_api_key"])
    ws_url = f"ws://127.0.0.1:{ws_port}"
    logger.info(f"🔗 WebSocket-Lauscher gestartet auf {ws_url}")
    
    while True:
        try:
            ws = websocket.WebSocketApp(ws_url, on_message=on_ws_message)
            ws.run_forever()
        except Exception as e:
            logger.error(f"WebSocket-Verbindung verloren: {e}")
        time.sleep(5) # Kurze Pause vor Wiederverbindung

def trigger_alert(settings):
    """Sendet den Alarm an das Eldercare-Backend."""
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
    
    logger.warning(f"🚨 ALARM! Sende Inaktivitäts-Warnung an Cloud (UUID: {event_uuid})...")
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        if r.status_code in [200, 201]:
            logger.info("✅ Cloud hat den Alarm bestätigt.")
            return True
        logger.error(f"❌ Cloud-Fehler: {r.status_code} - {r.text}")
    except Exception as e:
        logger.error(f"⚠️ Cloud nicht erreichbar: {e}")
    return False

if __name__ == "__main__":
    logger.info("🚀 Monitor-Dienst mit Funk- & Physisch-Erkennung gestartet.")
    
    # WebSocket im Hintergrund starten
    threading.Thread(target=websocket_thread, daemon=True).start()
    
    # Hauptschleife zur Überwachung des Timers
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
        
        # LOGIK: Wurde seit dem letzten Alarm etwas erkannt?
        if last_act > last_alr:
            # Normaler Modus: Wir warten auf das erste Überschreiten des Limits
            if (now - last_act) > timeout_seconds:
                if trigger_alert(settings):
                    set_alert_triggered()
                    logger.info("⏳ Alarm gesendet. Starte 1 Stunde Cooldown...")
        else:
            # Cooldown-Modus: Wir haben bereits alarmiert und keine neue Aktivität gesehen
            time_since_alert = now - last_alr
            cooldown = 3600 # 1 Stunde absolute Pause
            
            # Ist die Stunde rum?
            if time_since_alert > cooldown:
                # Jetzt muss erneut die volle Timeout-Zeit OHNE Aktivität vergehen
                # (Warten = Cooldown + Timeout)
                if time_since_alert > (cooldown + timeout_seconds):
                    logger.warning("Immer noch keine Aktivität nach Cooldown + Wartezeit!")
                    if trigger_alert(settings):
                        set_alert_triggered()
                        logger.info("⏳ Erneuter Alarm gesendet. Cooldown startet wieder...")
        
        time.sleep(10) # Den Timer alle 10 Sekunden prüfen