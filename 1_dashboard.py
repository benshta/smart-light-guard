import json, time, os, requests, sqlite3, subprocess
from flask import Flask, render_template_string, request, redirect

SETTINGS_FILE = "/opt/smart-light-guard/settings.json"
STATE_FILE = "/opt/smart-light-guard/state.json"
DECONZ_DB = "/root/.local/share/dresden-elektronik/deCONZ/zll.db"
DECONZ_HOST = "http://127.0.0.1:8080"
CLOUD_API = "https://eldercare.palffy.top/api/v1"

app = Flask(__name__)

def get_api_key_from_db():
    if not os.path.exists(DECONZ_DB): return None
    try:
        conn = sqlite3.connect(DECONZ_DB)
        cur = conn.cursor()
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

def save_json(filepath, data):
    with open(filepath, "w") as f: json.dump(data, f, indent=4)

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
    <title>Smart Light Guard - Setup</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: -apple-system, sans-serif; padding: 20px; background: #f0f2f5; }
        .card { background: white; padding: 20px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); max-width: 450px; margin: 0 auto 15px auto; }
        button { width: 100%; padding: 12px; border-radius: 6px; border: none; font-weight: bold; cursor: pointer; margin-top: 10px; }
        .btn-pair { background: #28a745; color: white; }
        .btn-save { background: #007bff; color: white; }
        .btn-cloud { background: #6f42c1; color: white; }
        .btn-danger { background: #dc3545; color: white; font-size: 0.8em; margin-top: 30px; }
        input { width: 100%; padding: 10px; margin: 8px 0; border: 1px solid #ddd; border-radius: 6px; box-sizing: border-box; }
        .status { padding: 10px; background: #e9ecef; border-radius: 6px; margin-bottom: 15px; font-family: monospace; font-size: 0.9em; word-break: break-all; }
    </style>
</head>
<body>
    <div class="card">
        <h2 style="text-align:center; color:#007bff;">🛡️ Smart Light Guard</h2>
        <form action="/pair" method="post"><button type="submit" class="btn-pair">➕ Zigbee-Gerät anlernen (60s)</button></form>
        <h3>📶 Sensoren</h3>
        {% for dev in devices %}
            <div style="padding:5px 0; border-bottom:1px solid #eee;">{{ dev.name }}</div>
        {% endfor %}
    </div>

    <div class="card">
        <h3>☁️ Cloud Backend Verbindung</h3>
        {% if settings.hub_id %}
            <div class="status">✅ Verbunden!<br>Hub ID: {{ settings.hub_id }}</div>
        {% else %}
            <div class="status" style="background:#fff3cd; color:#856404;">⚠️ Nicht registriert</div>
        {% endif %}
        
        <form action="/cloud_register" method="post">
            <p style="font-size:0.9em; color:#666;">Schnell-Registrierung (erstellt automatisch Haushalt & Hub):</p>
            <input type="email" name="email" placeholder="E-Mail Adresse" required>
            <input type="password" name="password" placeholder="Passwort" required>
            <input type="text" name="name" placeholder="Name (z.B. Oma Erna)" required>
            <button type="submit" class="btn-cloud">☁️ Am Server registrieren</button>
        </form>
    </div>

    <div class="card">
        <h3>⚙️ Lokale Einstellungen</h3>
        <form action="/save" method="post">
            <label>Inaktivitäts-Limit (Sekunden):</label>
            <input type="number" name="timeout_seconds" value="{{ settings.timeout_seconds }}">
            <button type="submit" class="btn-save">💾 Speichern</button>
        </form>

        <form action="/reset" method="post" onsubmit="return confirm('Wirklich ALLES löschen?');">
            <button type="submit" class="btn-danger">⚠️ System komplett zurücksetzen</button>
        </form>
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    settings = load_json(SETTINGS_FILE, {"timeout_seconds": 3600})
    api_key = settings.get("deconz_api_key") or get_api_key_from_db()
    if api_key and not settings.get("deconz_api_key"):
        settings["deconz_api_key"] = api_key
        save_json(SETTINGS_FILE, settings)
    
    devices = get_zigbee_devices(api_key)
    return render_template_string(HTML_TEMPLATE, settings=settings, devices=devices)

@app.route('/cloud_register', methods=['POST'])
def cloud_register():
    email = request.form['email']
    password = request.form['password']
    name = request.form['name']

    try:
        # 1. Registrieren (oder einloggen falls existiert)
        r = requests.post(f"{CLOUD_API}/auth/register", json={"email": email, "password": password})
        if r.status_code not in (200, 201):
            r = requests.post(f"{CLOUD_API}/auth/login", json={"email": email, "password": password})
        
        token = r.json().get("access_token")
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Haushalt erstellen
        r = requests.post(f"{CLOUD_API}/households", json={"name": f"Haushalt {name}"}, headers=headers)
        household_id = r.json().get("id")

        # 3. Hub erstellen
        r = requests.post(f"{CLOUD_API}/hubs", json={"household_id": household_id, "name": f"Hub {name}"}, headers=headers)
        hub_data = r.json()

        # 4. Speichern (Wir nehmen das Token als provisorischen API-Key, falls das Backend keinen eigenen schickt)
        settings = load_json(SETTINGS_FILE, {})
        settings["hub_id"] = hub_data.get("id") or hub_data.get("hub_id")
        settings["hub_api_key"] = token # Swagger Doku zeigt (noch) keinen separaten Hub-API-Key im Response
        settings["household_id"] = household_id
        save_json(SETTINGS_FILE, settings)

    except Exception as e:
        print(f"Fehler bei Registrierung: {e}")

    return redirect('/')

@app.route('/pair', methods=['POST'])
def pair():
    key = load_json(SETTINGS_FILE, {}).get("deconz_api_key")
    if key: requests.put(f"{DECONZ_HOST}/api/{key}/config", json={"permitjoin": 60})
    return redirect('/')

@app.route('/save', methods=['POST'])
def save():
    settings = load_json(SETTINGS_FILE, {})
    settings['timeout_seconds'] = int(request.form['timeout_seconds'])
    save_json(SETTINGS_FILE, settings)
    return redirect('/')

@app.route('/reset', methods=['POST'])
def reset():
    subprocess.run(["systemctl", "stop", "deconz"])
    subprocess.run(["rm", "-rf", "/root/.local/share/dresden-elektronik/deCONZ/"])
    if os.path.exists(SETTINGS_FILE): os.remove(SETTINGS_FILE)
    if os.path.exists(STATE_FILE): os.remove(STATE_FILE)
    subprocess.run(["systemctl", "start", "deconz"])
    return "System gelöscht. Lade Seite in 10 Sekunden neu."

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=80)