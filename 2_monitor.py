import json, time, os, subprocess
import websocket # Achtung: apt install python3-websocket

SETTINGS_FILE = "/opt/smart-light-guard/settings.json"
STATE_FILE = "/opt/smart-light-guard/state.json"
DECONZ_WS = "ws://127.0.0.1:443" # Standard Phoscon Websocket Port

def update_activity():
    state = {"last_activity": time.time(), "alert_sent": False}
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)
    print(f"Aktivität erkannt! Timer zurückgesetzt.")

def on_message(ws, message):
    data = json.loads(message)
    # Reagiere auf Sensor-Events oder Lichtschalter
    if data.get("e") == "changed" or data.get("e") == "added":
        update_activity()

def on_error(ws, error):
    print(f"Websocket Fehler: {error}")

def on_close(ws, close_status_code, close_msg):
    print("Websocket geschlossen. Versuche Neustart in 5s...")
    time.sleep(5)

# --- Haupt-Logik ---
if __name__ == "__main__":
    print("Starte SLG Monitor...")
    update_activity() # Initiale Aktivität setzen

    # Websocket in eigenem Prozess oder Thread starten, hier vereinfacht
    import threading
    ws = websocket.WebSocketApp(DECONZ_WS, on_message=on_message, on_error=on_error, on_close=on_close)
    wst = threading.Thread(target=ws.run_forever)
    wst.daemon = True
    wst.start()

    while True:
        try:
            with open(SETTINGS_FILE, "r") as f: settings = json.load(f)
            with open(STATE_FILE, "r") as f: state = json.load(f)
            
            timeout = settings.get("timeout_seconds", 3600)
            last_activity = state.get("last_activity", time.time())
            alert_sent = state.get("alert_sent", False)

            # Wenn Inaktivität das Limit überschreitet und noch kein Alarm gesendet wurde
            if (time.time() - last_activity) > timeout and not alert_sent:
                print("🚨 INAKTIVITÄT ERKANNT! LÖSE ALARM AUS...")
                
                # Rufe das Alarm-Skript auf
                subprocess.run(["python3", "/opt/smart-light-guard/4_alert_handler.py"])
                
                # Markiere als gesendet, bis wieder Bewegung erkannt wird
                state["alert_sent"] = True
                with open(STATE_FILE, "w") as f: json.dump(state, f)

        except Exception as e:
            pass # Dateien fehlen noch
            
        time.sleep(10) # Alle 10 Sekunden prüfen