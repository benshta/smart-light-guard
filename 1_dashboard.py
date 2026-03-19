import json, time, os, requests, sqlite3, subprocess, uuid
from flask import Flask, render_template_string, request, redirect
from slg_logger import get_logger

logger = get_logger("DASHBOARD")
SETTINGS_FILE = "/opt/smart-light-guard/settings.json"
DECONZ_HOST = "http://127.0.0.1:8080"
LOG_FILE = "/opt/smart-light-guard/system.log"

app = Flask(__name__)

def load_json(filepath):
    default = {
        "deconz_api_key": "",
        "backend": {"base_url": "https://eldercare.palffy.top/api/v1", "api_key": "", "hub_id": "", "household_id": ""},
        "alert_settings": {"timeout_seconds": 43200}
    }
    if os.path.exists(filepath):
        try:
            with open(filepath, "r") as f:
                data = json.load(f)
                default.update(data)
                if "backend" in data: default["backend"].update(data["backend"])
                if "alert_settings" in data: default["alert_settings"].update(data["alert_settings"])
                return default
        except Exception as e:
            logger.error(f"Fehler beim Laden der Settings: {e}")
    return default

def save_json(filepath, data):
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w") as f: json.dump(data, f, indent=4)
    except Exception as e:
        logger.error(f"Fehler beim Speichern der Settings: {e}")

def get_deconz_db_path():
    paths = [
        "/home/benji/.local/share/dresden-elektronik/deCONZ/zll.db",
        "/home/pi/.local/share/dresden-elektronik/deCONZ/zll.db",
        "/root/.local/share/dresden-elektronik/deCONZ/zll.db"
    ]
    for p in paths:
        if os.path.exists(p): return p
    return paths[0]

def force_inject_api_key():
    db_path = get_deconz_db_path()
    new_key = uuid.uuid4().hex[:16].upper()
    try:
        logger.info("Injiziere neuen deCONZ API-Key in die Datenbank...")
        subprocess.run(["systemctl", "stop", "deconz", "deconz-headless"], stderr=subprocess.DEVNULL)
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS auth (apikey TEXT PRIMARY KEY, devicetype TEXT, createdate TEXT, lastusedate TEXT, useragent TEXT)")
        cur.execute("INSERT OR IGNORE INTO auth (apikey, devicetype) VALUES (?, 'slg-dashboard')", (new_key,))
        conn.commit()
        conn.close()
        os.system(f"chmod -R 777 {os.path.dirname(db_path)}")
        subprocess.run(["systemctl", "start", "deconz"], stderr=subprocess.DEVNULL)
        time.sleep(5) # Etwas mehr Zeit für den Neustart geben
        logger.info("API-Key erfolgreich injiziert.")
        return new_key
    except Exception as e:
        logger.error(f"DB Fehler beim Key-Inject: {e}")
        return None

def get_or_create_api_key(settings):
    if settings.get("deconz_api_key"): return settings["deconz_api_key"]
    db_path = get_deconz_db_path()
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("SELECT apikey FROM auth LIMIT 1")
            row = cur.fetchone()
            conn.close()
            if row:
                settings["deconz_api_key"] = row[0]
                save_json(SETTINGS_FILE, settings)
                return row[0]
        except Exception as e:
            logger.warning(f"Konnte Key nicht aus DB lesen: {e}")
    
    key = force_inject_api_key()
    if key:
        settings["deconz_api_key"] = key
        save_json(SETTINGS_FILE, settings)
        return key
    return None

def get_zigbee_devices(api_key):
    devices = []
    if not api_key: return devices
    try:
        r = requests.get(f"{DECONZ_HOST}/api/{api_key}/sensors", timeout=3)
        if r.status_code == 200:
            for sid, data in r.json().items():
                if data.get("type") != "Daylight":
                    t = data.get("type", "")
                    if "Switch" in t: dev_type = "🔘 Schalter"
                    elif "Presence" in t: dev_type = "🏃 Bewegung"
                    elif "OpenClose" in t: dev_type = "🚪 Kontakt"
                    else: dev_type = "📡 Sensor"
                    devices.append({"name": data.get("name"), "type": dev_type})
        
        r2 = requests.get(f"{DECONZ_HOST}/api/{api_key}/lights", timeout=3)
        if r2.status_code == 200:
            for lid, data in r2.json().items():
                devices.append({"name": data.get("name"), "type": "💡 Licht/Aktor"})
    except requests.exceptions.RequestException as e:
        logger.error(f"Konnte Geräte nicht von deCONZ laden (deCONZ offline?): {e}")
    return devices

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Smart Light Guard</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: -apple-system, sans-serif; padding: 20px; background: #f4f6f9; color: #333; }
        .container { max-width: 500px; margin: 0 auto; }
        .card { background: white; padding: 25px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); margin-bottom: 20px; }
        h2 { margin-top: 0; font-size: 1.3em; border-bottom: 2px solid #f0f0f0; padding-bottom: 10px; }
        button { width: 100%; padding: 14px; border-radius: 8px; border: none; font-weight: bold; cursor: pointer; margin-top: 10px; transition: 0.2s; }
        button:hover { opacity: 0.9; }
        .btn-pair { background: #10b981; color: white; font-size: 1.1em; }
        .btn-cloud { background: #6366f1; color: white; }
        .btn-save { background: #3b82f6; color: white; }
        .btn-log { background: #475569; color: white; margin-top: 20px; }
        .btn-danger { background: #ef4444; color: white; margin-top: 10px; }
        input { width: 100%; padding: 12px; margin: 8px 0 15px 0; border: 1px solid #ddd; border-radius: 8px; box-sizing: border-box; }
        .status { padding: 12px; border-radius: 8px; margin-bottom: 15px; text-align: center; }
        .status-success { background: #d1fae5; color: #065f46; border: 1px solid #a7f3d0; }
        .status-error { background: #fee2e2; color: #991b1b; border: 1px solid #fecaca; }
        .device-list { background: #f8fafc; padding: 10px; border-radius: 8px; }
        .device-item { padding: 8px 0; border-bottom: 1px solid #e2e8f0; display: flex; justify-content: space-between;}
        .device-item:last-child { border-bottom: none; }
        .dev-type { color: #64748b; font-size: 0.85em; }
    </style>
    {% if request.args.get('pairing') %}
    <script>
        let timeLeft = 60;
        setInterval(() => {
            if(timeLeft <= 0) window.location.href = "/";
            document.getElementById("timer").innerText = --timeLeft;
        }, 1000);
    </script>
    {% endif %}
</head>
<body>
    <div class="container">
        <div class="card">
            <h2 style="color:#10b981;">🔌 Geräte & Sensoren</h2>
            {% if request.args.get('pairing') %}
                <div class="status status-success">
                    ⏳ <b>Pairing-Modus aktiv! (<span id="timer">60</span>s)</b><br>
                    <small>Bitte jetzt Gerät koppeln.</small>
                </div>
            {% else %}
                <form action="/pair" method="post"><button type="submit" class="btn-pair">➕ Gerät jetzt anlernen</button></form>
            {% endif %}
            
            <h3 style="margin-top:20px; font-size:1em; color:#64748b;">Verbunden:</h3>
            <div class="device-list">
            {% if devices %}
                {% for dev in devices %}
                <div class="device-item">
                    <span>✅ {{ dev.name }}</span>
                    <span class="dev-type">{{ dev.type }}</span>
                </div>
                {% endfor %}
            {% else %}
                <div style="color:#94a3b8; text-align:center;">Keine Geräte (Oder deCONZ startet noch)</div>
            {% endif %}
            </div>
        </div>

        <div class="card">
            <h2 style="color:#6366f1;">☁️ Server Anbindung</h2>
            {% if settings.backend.hub_id %}
                <div class="status status-success">✅ Verbunden (Hub ID: {{ settings.backend.hub_id[:8] }}...)</div>
            {% else %}
                <div class="status status-error">⚠️ Noch nicht registriert</div>
                <form action="/cloud_register" method="post">
                    <input type="email" name="email" placeholder="E-Mail Adresse" required>
                    <input type="password" name="password" placeholder="Passwort" required>
                    <input type="text" name="name" placeholder="Name (z.B. Haushalt Huber)" required>
                    <button type="submit" class="btn-cloud">Am Server registrieren</button>
                </form>
            {% endif %}
        </div>

        <div class="card">
            <h2 style="color:#3b82f6;">⚙️ Lokale Einstellungen</h2>
            <form action="/save" method="post">
                <label style="font-size:0.9em; color:#475569;">Inaktivitäts-Limit (Sekunden):</label>
                <input type="number" name="timeout_seconds" value="{{ settings.alert_settings.timeout_seconds }}">
                <button type="submit" class="btn-save">💾 Speichern</button>
            </form>
            <form action="/logs" method="get"><button type="submit" class="btn-log">📜 System-Logs ansehen</button></form>
            <form action="/reset" method="post" onsubmit="return confirm('Wirklich ALLES löschen?');"><button type="submit" class="btn-danger">⚠️ System zurücksetzen</button></form>
        </div>
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    settings = load_json(SETTINGS_FILE)
    api_key = get_or_create_api_key(settings)
    devices = get_zigbee_devices(api_key)
    return render_template_string(HTML_TEMPLATE, settings=settings, devices=devices)

@app.route('/pair', methods=['POST'])
def pair():
    settings = load_json(SETTINGS_FILE)
    api_key = settings.get("deconz_api_key")
    if api_key:
        try:
            r = requests.put(f"{DECONZ_HOST}/api/{api_key}/config", json={"permitjoin": 60}, timeout=5)
            r.raise_for_status()
            logger.info("Pairing-Modus aktiviert.")
            return redirect('/?pairing=true')
        except Exception as e:
            logger.error(f"Fehler beim Aktivieren des Pairing-Modus: {e}")
    return redirect('/?error=nokey')

@app.route('/cloud_register', methods=['POST'])
def cloud_register():
    email = request.form['email']
    password = request.form['password']
    name = request.form['name']
    settings = load_json(SETTINGS_FILE)
    base_url = settings["backend"]["base_url"]
    
    logger.info(f"Versuche Cloud-Registrierung für '{name}'...")
    try:
        # Auth
        r = requests.post(f"{base_url}/auth/register", json={"email": email, "password": password})
        if r.status_code not in (200, 201):
            r = requests.post(f"{base_url}/auth/login", json={"email": email, "password": password})
        r.raise_for_status() # Bricht hart ab und loggt Fehler, falls Auth fehlschlägt
        token = r.json().get("access_token")
        headers = {"Authorization": f"Bearer {token}"}
        
        # Household
        r_hh = requests.post(f"{base_url}/households", json={"name": name, "inactivity_threshold_hours": 12}, headers=headers)
        r_hh.raise_for_status()
        household_id = r_hh.json().get("id")
        
        # Hub
        r_hub = requests.post(f"{base_url}/hubs", json={"household_id": household_id, "name": f"Hub {name}"}, headers=headers)
        r_hub.raise_for_status()
        
        settings["backend"]["hub_id"] = r_hub.json().get("id")
        settings["backend"]["api_key"] = r_hub.json().get("api_key") # Der echte API Key!
        settings["backend"]["household_id"] = household_id
        save_json(SETTINGS_FILE, settings)
        logger.info(f"Cloud-Registrierung ERFOLGREICH! Hub-ID: {settings['backend']['hub_id']}")
    except requests.exceptions.HTTPError as err:
        logger.error(f"Cloud-Fehler: {err.response.status_code} - {err.response.text}")
    except Exception as e:
        logger.error(f"Allgemeiner Fehler bei Cloud-Registrierung: {e}")
        
    return redirect('/')

@app.route('/save', methods=['POST'])
def save():
    settings = load_json(SETTINGS_FILE)
    new_timeout = int(request.form['timeout_seconds'])
    settings["alert_settings"]["timeout_seconds"] = new_timeout
    save_json(SETTINGS_FILE, settings)
    logger.info(f"Lokale Einstellungen gespeichert. Neues Timeout: {new_timeout}s")
    return redirect('/')

@app.route('/reset', methods=['POST'])
def reset():
    logger.warning("Führe System-Reset durch!")
    subprocess.run(["systemctl", "stop", "deconz"])
    subprocess.run(["rm", "-rf", "/root/.local/share/dresden-elektronik/deCONZ/"])
    subprocess.run(["rm", "-rf", "/home/benji/.local/share/dresden-elektronik/deCONZ/"])
    if os.path.exists(SETTINGS_FILE): os.remove(SETTINGS_FILE)
    subprocess.run(["systemctl", "start", "deconz"])
    return "System gelöscht. Bitte Seite manuell neu laden (F5)."

@app.route('/logs')
def show_logs():
    try:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r") as f:
                lines = f.readlines()[-100:]
                lines.reverse()
                log_text = "".join(lines)
        else:
            log_text = "Log-Datei existiert nicht."
    except Exception as e:
        log_text = f"Fehler: {e}"
    return f"<html><body style='background:#1e1e1e;color:#0f0;font-family:monospace;'><a href='/' style='color:#3b82f6;'>🔙 Zurück</a><pre>{log_text}</pre></body></html>"

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=80, threaded=True)