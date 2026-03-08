import json, time, os, requests, sqlite3, subprocess
from flask import Flask, render_template_string, request, redirect

# Pfade
SETTINGS_FILE = "settings.json"
STATE_FILE = "state.json"
DECONZ_DB = "/root/.local/share/dresden-elektronik/deCONZ/zll.db"
DECONZ_HOST = "http://127.0.0.1:8080"

app = Flask(__name__)

def get_api_key_from_db():
    """Extrahiert den API-Key direkt aus der deCONZ Datenbank (kein Klick nötig)"""
    if not os.path.exists(DECONZ_DB): return None
    try:
        conn = sqlite3.connect(DECONZ_DB)
        cur = conn.cursor()
        # Suche nach einem API-Key in der auth Tabelle
        cur.execute("SELECT apikey FROM auth LIMIT 1")
        row = cur.fetchone()
        conn.close()
        return row[0] if row else None
    except: return None

def load_json(filepath, default):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r") as f: return json.load(f)
        except: pass
    return default

def get_zigbee_devices(api_key):
    devices = []
    if not api_key: return devices
    try:
        r = requests.get(f"{DECONZ_HOST}/api/{api_key}/sensors", timeout=2)
        if r.status_code == 200:
            for sid, data in r.json().items():
                if data.get("type") not in ["Daylight", "ZHASwitch"]:
                    devices.append({"name": data.get("name"), "type": "Sensor"})
    except: pass
    return devices

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Smart Light Guard</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: -apple-system, sans-serif; padding: 20px; background: #f0f2f5; }
        .card { background: white; padding: 20px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); max-width: 450px; margin: 0 auto 15px auto; }
        button { width: 100%; padding: 12px; border-radius: 6px; border: none; font-weight: bold; cursor: pointer; margin-top: 10px; }
        .btn-pair { background: #28a745; color: white; }
        .btn-save { background: #007bff; color: white; }
        .btn-danger { background: #dc3545; color: white; font-size: 0.8em; margin-top: 30px; }
        input, select { width: 100%; padding: 10px; margin: 8px 0; border: 1px solid #ddd; border-radius: 6px; box-sizing: border-box; }
        .device-item { padding: 10px 0; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; }
    </style>
</head>
<body>
    <div class="card">
        <h2 style="text-align:center; color:#007bff;">🛡️ Smart Light Guard</h2>
        <p style="text-align:center;">Status: <strong>Verbunden</strong></p>
        
        <form action="/pair" method="post"><button type="submit" class="btn-pair">➕ Gerät jetzt anlernen (60s)</button></form>
        
        <h3>📶 Geräte</h3>
        {% for dev in devices %}
            <div class="device-item"><span>{{ dev.name }}</span> <small>{{ dev.type }}</small></div>
        {% endfor %}
    </div>

    <div class="card">
        <h3>⚙️ Einstellungen</h3>
        <form action="/save" method="post">
            <label>Limit (Sekunden):</label>
            <input type="number" name="timeout_seconds" value="{{ settings.timeout_seconds }}">
            <label>Nummern:</label>
            <input type="text" name="contacts_raw" value="{{ contacts_str }}">
            <button type="submit" class="btn-save">Speichern</button>
        </form>

        <form action="/reset" method="post" onsubmit="return confirm('Wirklich alle Geräte und das Gateway löschen?');">
            <button type="submit" class="btn-danger">⚠️ System komplett zurücksetzen</button>
        </form>
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    # Versuche API-Key automatisch zu finden, falls nicht in Settings
    settings = load_json(SETTINGS_FILE, {"timeout_seconds": 3600, "contacts": []})
    api_key = settings.get("deconz_api_key") or get_api_key_from_db()
    
    # Falls wir einen Key gefunden haben, den wir noch nicht gespeichert hatten:
    if api_key and not settings.get("deconz_api_key"):
        settings["deconz_api_key"] = api_key
        with open(SETTINGS_FILE, "w") as f: json.dump(settings, f)

    contacts_str = ", ".join([c["number"] for c in settings.get("contacts", [])])
    devices = get_zigbee_devices(api_key)
    return render_template_string(HTML_TEMPLATE, settings=settings, contacts_str=contacts_str, devices=devices)

@app.route('/pair', methods=['POST'])
def pair():
    key = load_json(SETTINGS_FILE, {}).get("deconz_api_key")
    if key: requests.put(f"{DECONZ_HOST}/api/{key}/config", json={"permitjoin": 60})
    return redirect('/')

@app.route('/reset', methods=['POST'])
def reset():
    # Gateway plattmachen
    subprocess.run(["systemctl", "stop", "deconz"])
    subprocess.run(["rm", "-rf", "/root/.local/share/dresden-elektronik/deCONZ/"])
    # Settings & State löschen
    if os.path.exists(SETTINGS_FILE): os.remove(SETTINGS_FILE)
    if os.path.exists(STATE_FILE): os.remove(STATE_FILE)
    subprocess.run(["systemctl", "start", "deconz"])
    return "System wurde zurückgesetzt. Bitte Seite in 10 Sekunden neu laden."

@app.route('/save', methods=['POST'])
def save():
    settings = load_json(SETTINGS_FILE, {})
    settings['timeout_seconds'] = int(request.form['timeout_seconds'])
    raw_numbers = [n.strip() for n in request.form['contacts_raw'].split(',') if n.strip()]
    settings['contacts'] = [{"number": num, "priority": i+1} for i, num in enumerate(raw_numbers)]
    with open(SETTINGS_FILE, "w") as f: json.dump(settings, f)
    return redirect('/')

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=80)