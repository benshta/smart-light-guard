import json, time, os, requests, sqlite3, subprocess, uuid
from flask import Flask, render_template_string, request, redirect

SETTINGS_FILE = "/opt/smart-light-guard/settings.json"
STATE_FILE = "/opt/smart-light-guard/state.json"
DECONZ_HOST = "http://127.0.0.1:8080"
CLOUD_API = "https://eldercare.palffy.top/api/v1"

app = Flask(__name__)

def get_deconz_db_path():
    """Sucht die DB im richtigen Benutzerordner (benji, pi, root)"""
    paths = [
        "/home/benji/.local/share/dresden-elektronik/deCONZ/zll.db",
        "/home/pi/.local/share/dresden-elektronik/deCONZ/zll.db",
        "/var/lib/deconz/.local/share/dresden-elektronik/deCONZ/zll.db",
        "/root/.local/share/dresden-elektronik/deCONZ/zll.db"
    ]
    for p in paths:
        if os.path.exists(p): return p
    return paths[0] # Fallback auf benji

def force_inject_api_key():
    db_path = get_deconz_db_path()
    new_key = uuid.uuid4().hex[:16].upper()
    try:
        subprocess.run(["systemctl", "stop", "deconz", "deconz-headless"], stderr=subprocess.DEVNULL)
        
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS auth (apikey TEXT PRIMARY KEY, devicetype TEXT, createdate TEXT, lastusedate TEXT, useragent TEXT)")
        cur.execute("INSERT OR IGNORE INTO auth (apikey, devicetype) VALUES (?, 'slg-dashboard')", (new_key,))
        conn.commit()
        conn.close()
        
        # BERECHTIGUNGEN REPARIEREN: Wichtig, damit der normale User die Datei lesen darf
        os.system(f"chmod -R 777 {os.path.dirname(db_path)}")
        
        subprocess.run(["systemctl", "start", "deconz"], stderr=subprocess.DEVNULL)
        time.sleep(4) # Gateway kurz Zeit zum Hochfahren geben
        return new_key
    except Exception as e:
        print(f"DB Fehler: {e}")
        return None

def get_or_create_api_key():
    settings = load_json(SETTINGS_FILE, {})
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
        except: pass
        
    key = force_inject_api_key()
    if key:
        settings["deconz_api_key"] = key
        save_json(SETTINGS_FILE, settings)
        return key
    return None

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
        # 1. Sensoren abrufen
        r = requests.get(f"{DECONZ_HOST}/api/{api_key}/sensors", timeout=2)
        if r.status_code == 200:
            for sid, data in r.json().items():
                if data.get("type") not in ["Daylight", "ZHASwitch"]:
                    devices.append({"name": data.get("name"), "type": "Sensor"})
        
        # 2. Lampen & Steckdosen abrufen
        r2 = requests.get(f"{DECONZ_HOST}/api/{api_key}/lights", timeout=2)
        if r2.status_code == 200:
            for lid, data in r2.json().items():
                devices.append({"name": data.get("name"), "type": "Licht/Aktor"})
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
        .btn-pair { background: #28a745; color: white; font-size: 1.1em; }
        .btn-save { background: #007bff; color: white; }
        .btn-cloud { background: #6f42c1; color: white; }
        .btn-danger { background: #dc3545; color: white; font-size: 0.8em; margin-top: 30px; }
        input { width: 100%; padding: 10px; margin: 8px 0; border: 1px solid #ddd; border-radius: 6px; box-sizing: border-box; }
        .status { padding: 10px; border-radius: 6px; margin-bottom: 15px; }
        .status-cloud { background: #e9ecef; font-family: monospace; font-size: 0.9em; word-break: break-all; }
        .banner-success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; text-align: center; font-size: 1.1em; padding: 15px; }
        .banner-error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; text-align: center; }
    </style>
    {% if request.args.get('pairing') %}
    <script>
        let timeLeft = 60;
        let timerId = setInterval(countdown, 1000);
        function countdown() {
            if (timeLeft == 0) {
                clearTimeout(timerId);
                window.location.href = "/";
            } else {
                document.getElementById("timer").innerHTML = timeLeft;
                timeLeft--;
            }
        }
    </script>
    {% endif %}
</head>
<body>
    <div class="card">
        <h2 style="text-align:center; color:#28a745;">🔌 1. Zigbee-Sensoren</h2>
        
        {% if request.args.get('pairing') %}
            <div class="status banner-success">
                ⏳ <b>Pairing-Modus aktiv! (<span id="timer">60</span>s)</b><br>
                <small>Bitte drücke jetzt den Reset-Knopf an deinem Sensor.</small>
            </div>
        {% elif request.args.get('error') == 'nokey' %}
            <div class="status banner-error">❌ <b>Gateway-Zugriff fehlgeschlagen.</b><br>API-Verbindung verweigert.</div>
        {% else %}
            <form action="/pair" method="post">
                <button type="submit" class="btn-pair">➕ Sensor jetzt anlernen</button>
            </form>
        {% endif %}

        <h3 style="margin-top: 20px;">📶 Verbundene Geräte</h3>
        {% if devices %}
            {% for dev in devices %}
                <div style="padding:8px 0; border-bottom:1px solid #eee;">✅ {{ dev.name }}</div>
            {% endfor %}
        {% else %}
            <p style="color:#666; font-size:0.9em; text-align:center;">Noch keine Geräte angelernt.</p>
        {% endif %}
    </div>

    <div class="card">
        <h2 style="text-align:center; color:#6f42c1;">☁️ 2. Cloud Server</h2>
        {% if settings.hub_id %}
            <div class="status status-cloud">✅ Hub verbunden!<br>ID: {{ settings.hub_id }}</div>
        {% else %}
            <div class="status banner-error">⚠️ Hub ist noch nicht beim Server registriert.</div>
            <form action="/cloud_register" method="post">
                <input type="email" name="email" placeholder="E-Mail Adresse" required>
                <input type="password" name="password" placeholder="Passwort" required>
                <input type="text" name="name" placeholder="Name (z.B. Oma Erna)" required>
                <button type="submit" class="btn-cloud">☁️ Am Server registrieren</button>
            </form>
        {% endif %}
    </div>

    <div class="card">
        <h2 style="text-align:center; color:#007bff;">⚙️ 3. Einstellungen</h2>
        <form action="/save" method="post">
            <label>Inaktivitäts-Limit (Sekunden):</label>
            <input type="number" name="timeout_seconds" value="{{ settings.timeout_seconds }}">
            <label>Notfall-Nummern (Komma-getrennt):</label>
            <input type="text" name="contacts_raw" value="{{ contacts_str }}" placeholder="+41791234567, +41781234567">
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
    settings = load_json(SETTINGS_FILE, {"timeout_seconds": 3600, "contacts": []})
    api_key = get_or_create_api_key()
    devices = get_zigbee_devices(api_key)
    contacts_str = ", ".join([c["number"] for c in settings.get("contacts", [])])
    return render_template_string(HTML_TEMPLATE, settings=settings, contacts_str=contacts_str, devices=devices)

@app.route('/pair', methods=['POST'])
def pair():
    api_key = get_or_create_api_key()
    if api_key:
        try:
            r = requests.put(f"{DECONZ_HOST}/api/{api_key}/config", json={"permitjoin": 60}, timeout=5)
            if r.status_code == 200:
                return redirect('/?pairing=true')
        except Exception as e:
            print(f"Fehler bei deCONZ Anfrage: {e}")
    return redirect('/?error=nokey')

@app.route('/cloud_register', methods=['POST'])
def cloud_register():
    email = request.form['email']
    password = request.form['password']
    name = request.form['name']
    try:
        r = requests.post(f"{CLOUD_API}/auth/register", json={"email": email, "password": password})
        if r.status_code not in (200, 201):
            r = requests.post(f"{CLOUD_API}/auth/login", json={"email": email, "password": password})
        
        token = r.json().get("access_token")
        headers = {"Authorization": f"Bearer {token}"}
        r = requests.post(f"{CLOUD_API}/households", json={"name": f"Haushalt {name}"}, headers=headers)
        household_id = r.json().get("id")
        r = requests.post(f"{CLOUD_API}/hubs", json={"household_id": household_id, "name": f"Hub {name}"}, headers=headers)
        
        settings = load_json(SETTINGS_FILE, {})
        settings["hub_id"] = r.json().get("id") or r.json().get("hub_id")
        settings["hub_api_key"] = token 
        settings["household_id"] = household_id
        save_json(SETTINGS_FILE, settings)
    except: pass
    return redirect('/')

@app.route('/save', methods=['POST'])
def save():
    settings = load_json(SETTINGS_FILE, {})
    settings['timeout_seconds'] = int(request.form['timeout_seconds'])
    raw_numbers = [n.strip() for n in request.form['contacts_raw'].split(',') if n.strip()]
    settings['contacts'] = [{"number": num, "priority": i+1} for i, num in enumerate(raw_numbers)]
    settings['local_update_timestamp'] = time.time()
    save_json(SETTINGS_FILE, settings)
    return redirect('/')

@app.route('/reset', methods=['POST'])
def reset():
    subprocess.run(["systemctl", "stop", "deconz", "deconz-headless"])
    subprocess.run(["rm", "-rf", "/root/.local/share/dresden-elektronik/deCONZ/"])
    subprocess.run(["rm", "-rf", "/home/benji/.local/share/dresden-elektronik/deCONZ/"])
    if os.path.exists(SETTINGS_FILE): os.remove(SETTINGS_FILE)
    if os.path.exists(STATE_FILE): os.remove(STATE_FILE)
    subprocess.run(["systemctl", "start", "deconz"])
    return "System gelöscht. Lade Seite in 10 Sekunden neu."

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=80)