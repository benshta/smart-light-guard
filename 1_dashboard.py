import json
import time
import os
import requests
import logging
from flask import Flask, render_template_string, request, redirect

log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

SETTINGS_FILE = "settings.json"
STATE_FILE = "state.json"
DECONZ_HOST = "http://127.0.0.1:8080"

app = Flask(__name__)

def load_json(filepath, default):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r") as f:
                return json.load(f)
        except: pass
    return default

def save_settings(data):
    data["updated_at"] = time.time()
    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_zigbee_devices(api_key):
    devices = []
    if not api_key: return devices
    try:
        r_sens = requests.get(f"{DECONZ_HOST}/api/{api_key}/sensors", timeout=2)
        if r_sens.status_code == 200:
            for sid, data in r_sens.json().items():
                if data.get("type") != "Daylight":
                    devices.append({"name": data.get("name"), "type": "Sensor"})
        
        r_lights = requests.get(f"{DECONZ_HOST}/api/{api_key}/lights", timeout=2)
        if r_lights.status_code == 200:
            for lid, data in r_lights.json().items():
                devices.append({"name": data.get("name"), "type": "Lampe / Aktor"})
    except: pass
    return devices

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Smart Light Guard</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: -apple-system, sans-serif; padding: 20px; background: #f0f2f5; color: #1c1e21; }
        .card { background: white; padding: 25px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); max-width: 450px; margin: 0 auto 20px auto; }
        h1 { text-align: center; color: #007bff; }
        label { display: block; margin-top: 15px; font-weight: bold; font-size: 0.9em; color: #555; }
        input, select { width: 100%; padding: 12px; margin: 8px 0; border: 1px solid #ccc; border-radius: 6px; box-sizing: border-box; }
        button { background: #007bff; color: white; border: none; padding: 14px; border-radius: 6px; cursor: pointer; width: 100%; font-weight: bold; font-size: 16px; margin-bottom: 10px; }
        button.pair { background: #28a745; }
        button.phoscon { background: #6c757d; }
        .status-box { background: #e7f3ff; padding: 15px; border-radius: 8px; text-align: center; border: 1px solid #b3d7ff; margin-bottom: 20px; font-size: 1.1em; }
        .alert-success { background: #d4edda; color: #155724; padding: 15px; border-radius: 8px; margin-bottom: 20px; text-align: center; border: 1px solid #c3e6cb; }
        .alert-warning { background: #fff3cd; color: #856404; padding: 15px; border-radius: 8px; margin-bottom: 20px; border: 1px solid #ffeeba; }
        .device-list { list-style: none; padding: 0; margin: 15px 0 0 0; }
        .device-item { padding: 12px 0; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; align-items: center; }
        .device-type { color: #888; font-size: 0.8em; background: #f8f9fa; padding: 4px 8px; border-radius: 4px; }
    </style>
</head>
<body>
    <h1>🛡️ Smart Light Guard</h1>
    
    {% if msg == 'apikey_success' %}
        <div class="alert-success">✅ API-Key erfolgreich generiert! Das System ist verbunden.</div>
    {% elif msg == 'apikey_failed' %}
        <div class="alert-warning">❌ Fehler: Hast du in Phoscon auf "App verbinden" geklickt?</div>
    {% endif %}

    {% if not api_key %}
    <div class="alert-warning">
        <strong>⚠️ Gateway nicht verbunden</strong><br><br>
        1. Öffne die <a href="http://{{ request.host.split(':')[0] }}:8080/pwa/index.html" target="_blank">Phoscon App</a><br>
        2. Gehe zu Einstellungen -> Gateway -> Erweitert<br>
        3. Klicke auf <b>App verbinden</b><br>
        4. Kehre sofort hierher zurück und klicke diesen Button:
        <form action="/fetch_api_key" method="post" style="margin-top: 15px;">
            <button type="submit">🔑 API-Key anfordern</button>
        </form>
    </div>
    {% endif %}

    {% if pairing_active %}
    <div class="alert-success">
        <strong>⏳ Pairing-Modus aktiv!</strong><br>Gerät jetzt einschalten/Reset drücken.
    </div>
    {% endif %}

    <div class="card status-box">Letzte registrierte Aktivität:<br><strong>{{ last_act_time }}</strong></div>

    <div class="card">
        {% if api_key %}
            <form action="/pair" method="post"><button type="submit" class="pair">➕ Neues Gerät anlernen (60s)</button></form>
        {% endif %}
        <button class="phoscon" onclick="window.open('http://{{ request.host.split(':')[0] }}:8080/pwa/index.html', '_blank')">⚙️ Geräteverwaltung (Phoscon)</button>
        
        <h3 style="margin-top: 25px;">📶 Verbundene Geräte</h3>
        {% if devices %}
            <ul class="device-list">
            {% for dev in devices %}
                <li class="device-item"><strong>{{ dev.name }}</strong><span class="device-type">{{ dev.type }}</span></li>
            {% endfor %}
            </ul>
        {% else %}
            <p style="color: #888; text-align: center; margin-top: 15px;">{% if api_key %}Keine Geräte gefunden.{% else %}Warte auf API-Key...{% endif %}</p>
        {% endif %}
    </div>

    <div class="card">
        <h3 style="margin-top: 0;">⚙️ Einstellungen</h3>
        <form action="/save" method="post">
            <label>Inaktivitäts-Limit (Sekunden):</label>
            <input type="number" name="timeout_seconds" value="{{ settings.timeout_seconds }}" min="10">
            <label>Benachrichtigungs-Modus:</label>
            <select name="notification_mode">
                <option value="all" {% if settings.notification_mode == 'all' %}selected{% endif %}>Alle gleichzeitig alarmieren</option>
                <option value="sequential" {% if settings.notification_mode == 'sequential' %}selected{% endif %}>Nach Priorität eskalieren</option>
            </select>
            <label>Notfall-Nummern (Komma getrennt):</label>
            <input type="text" name="contacts_raw" value="{{ contacts_str }}">
            <button type="submit" style="margin-top: 15px;">Konfiguration speichern</button>
        </form>
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    pairing_active = request.args.get('pairing') == 'true'
    msg = request.args.get('msg')
    
    settings = load_json(SETTINGS_FILE, {"timeout_seconds": 3600, "notification_mode": "all", "contacts": []})
    state = load_json(STATE_FILE, {"last_activity": time.time()})
    
    api_key = settings.get("deconz_api_key", "")
    contacts_str = ", ".join([c["number"] for c in settings.get("contacts", [])])
    last_act = time.strftime('%H:%M:%S', time.localtime(state.get("last_activity", time.time())))
    
    devices = get_zigbee_devices(api_key)
    
    return render_template_string(HTML_TEMPLATE, settings=settings, contacts_str=contacts_str, last_act_time=last_act, pairing_active=pairing_active, devices=devices, api_key=api_key, msg=msg)

@app.route('/fetch_api_key', methods=['POST'])
def fetch_api_key():
    try:
        # Fragt bei deCONZ einen neuen, offiziellen API-Key an
        r = requests.post(f"{DECONZ_HOST}/api", json={"devicetype": "slg-dashboard"}, timeout=5)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and "success" in data[0]:
                new_key = data[0]["success"]["username"]
                settings = load_json(SETTINGS_FILE, {})
                settings["deconz_api_key"] = new_key
                save_settings(settings)
                return redirect('/?msg=apikey_success')
    except: pass
    return redirect('/?msg=apikey_failed')

@app.route('/save', methods=['POST'])
def save():
    settings = load_json(SETTINGS_FILE, {})
    settings['timeout_seconds'] = int(request.form['timeout_seconds'])
    settings['notification_mode'] = request.form['notification_mode']
    raw_numbers = [n.strip() for n in request.form['contacts_raw'].split(',') if n.strip()]
    settings['contacts'] = [{"number": num, "priority": i+1} for i, num in enumerate(raw_numbers)]
    save_settings(settings)
    return redirect('/')

@app.route('/pair', methods=['POST'])
def pair():
    settings = load_json(SETTINGS_FILE, {})
    api_key = settings.get("deconz_api_key", "")
    if api_key:
        try:
            requests.put(f"{DECONZ_HOST}/api/{api_key}/config", json={"permitjoin": 60}, timeout=5)
        except: pass
    return redirect('/?pairing=true')

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=80, threaded=True)