import websocket
import json
import threading
import time
import os
from importlib import import_module

alert_handler = import_module("4_alert_handler")

SETTINGS_FILE = "settings.json"
STATE_FILE = "state.json"
API_KEY = "3B80CF27C6"
WS_URL = f"ws://127.0.0.1:8080/?api_key={API_KEY}"

settings_cache = {}
last_settings_mtime = 0
state_cache = {"last_activity": time.time(), "alert_sent": False}
last_state_write = 0

def load_settings_hot_reload():
    global settings_cache, last_settings_mtime
    try:
        current_mtime = os.path.getmtime(SETTINGS_FILE)
        if current_mtime > last_settings_mtime:
            with open(SETTINGS_FILE, "r") as f:
                settings_cache = json.load(f)
            last_settings_mtime = current_mtime
            print("🔄 [MONITOR] Neue Settings geladen.")
    except: pass

def save_state_throttled(force=False):
    global last_state_write
    current_time = time.time()
    if force or (current_time - last_state_write > 60):
        try:
            with open(STATE_FILE, "w") as f:
                json.dump(state_cache, f)
            last_state_write = current_time
        except: pass

def load_initial_state():
    global state_cache
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                state_cache = json.load(f)
        except: pass

def watchdog_timer():
    while True:
        load_settings_hot_reload()
        timeout = settings_cache.get("timeout_seconds", 3600)
        elapsed = time.time() - state_cache['last_activity']
        
        if elapsed > timeout and not state_cache['alert_sent']:
            if alert_handler.send_alarm(settings_cache, elapsed):
                state_cache['alert_sent'] = True
                save_state_throttled(force=True)
        time.sleep(5)

def on_message(ws, message):
    data = json.loads(message)
    if data.get("e") == "changed":
        state = data.get("state", {})
        resource = data.get("r")
        
        is_activity = False
        if resource == "sensors" and any(k in state for k in ["presence", "buttonevent", "open", "vibration"]):
            is_activity = True
        elif resource == "lights" and ("on" in state or "reachable" in state):
            is_activity = True

        if is_activity:
            state_cache['last_activity'] = time.time()
            state_cache['alert_sent'] = False
            save_state_throttled()
            print(f">>> [ACTIVITY] {resource.upper()} erkannt.")

def run_websocket():
    while True:
        try:
            ws = websocket.WebSocketApp(WS_URL, on_message=on_message)
            ws.run_forever()
        except: pass
        time.sleep(5)

if __name__ == "__main__":
    print("🚀 Monitor gestartet...")
    load_initial_state()
    if os.path.exists(SETTINGS_FILE):
        load_settings_hot_reload()
    else:
        settings_cache = {"timeout_seconds": 3600, "contacts": []}
        
    threading.Thread(target=run_websocket, daemon=True).start()
    watchdog_timer()