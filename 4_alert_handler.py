import requests
import time

def send_alarm(settings, idle_time):
    payload = {
        "event_type": "inactivity_alarm",
        "device_id": "smart-light-guard-poc",
        "idle_duration_seconds": int(idle_time),
        "notification_mode": settings.get("notification_mode", "all"),
        "contacts": settings.get("contacts", []),
        "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    }
    
    try:
        print(f"🚨 Sende Alarm an Backend (Modus: {payload['notification_mode']})...")
        r = requests.post("https://n8n.benjamin-stadelmann.ch/webhook/37c506a1-cdde-404f-9517-9db90cc76ceb", json=payload, timeout=5)
        if 200 <= r.status_code < 300:
            print("✅ Alarm erfolgreich an API übermittelt.")
            return True
    except Exception as e:
        print(f"❌ Alarm-Versand fehlgeschlagen: {e}")
    return False