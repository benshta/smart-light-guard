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
API_KEY = "3B80CF27C6"
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

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Smart Light Guard</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: sans-serif; padding: 20px; background: #f0f2f5; color: #1c1e21; }
        .card { background: white; padding: 25px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); max-width: 450px; margin: 0 auto 20px auto; }
        h1 { text-align: center; color: #007bff; }
        label { display: block; margin-top: 15px; font-weight: bold; }
        input, select { width: 100%; padding: 12px; margin: 8px 0; border: 1px solid #ccc; border-radius: 6px; box-sizing: border-box; }
        button { background: #007bff; color: white; border: none; padding: 14px; border-radius: 6px; cursor: pointer; width: 100%; font-weight: bold; }
        button.pair { background: #28a745; margin-bottom: 20px; }
        .status-box { background: #e7f3ff; padding: 15px; border-radius: 8px; text-align: center; border: 1px solid #b3d7ff; }
    </style>
</head>
<body>
    <h1>🛡️ Smart Light Guard</h1>
    <div class="card">
        <form action="/pair" method="post"><button type="submit" class="pair">➕ Gerät koppeln (60s)</button></form>
        <hr style="border:0; border-top:1px solid #eee; margin: 20px 0;">
        <form action="/save" method="post">
            <label>Inaktivitäts-Limit (Sekunden):</label>
            <input type="number" name="timeout_seconds" value="{{ settings.timeout_seconds }}" min="10">
            
            <label>Benachrichtigungs-Modus:</label>
            <select name="notification_mode">
                <option value="all" {% if settings.notification_mode == 'all' %}selected{% endif %}>Alle gleichzeitig informieren</option>
                <option value="sequential" {% if settings.notification_mode == 'sequential' %}selected{% endif %}>Nach Priorität eskalieren</option>
            </select>

            <label>Notfall-Nummern (Komma getrennt für POC):</label>
            <input type="text" name="contacts_raw" value="{{ contacts_str }}" placeholder="+4179..., +4178...">
            
            <button type="submit">Speichern</button>
        </form>
    </div>
    <div class="card status-box">Letzte Aktivität: <strong>{{ last_act_time }}</strong></div>
</body>
</html>
"""

@app.route('/')
def index():
    settings = load_json(SETTINGS_FILE, {"timeout_seconds": 3600, "notification_mode": "all", "contacts": []})
    state = load_json(STATE_FILE, {"last_activity": time.time()})
    contacts_str = ", ".join([c["number"] for c in settings.get("contacts", [])])
    last_act = time.strftime('%H:%M:%S', time.localtime(state.get("last_activity", time.time())))
    return render_template_string(HTML_TEMPLATE, settings=settings, contacts_str=contacts_str, last_act_time=last_act)

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
    try:
        requests.put(f"{DECONZ_HOST}/api/{API_KEY}/config", json={"permitjoin": 60}, timeout=5)
    except: pass
    return "Pairing aktiv (60s)! <a href='/'>Zurück</a>"

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=80, threaded=True)