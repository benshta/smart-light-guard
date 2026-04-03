import json
import time
import subprocess
import xml.etree.ElementTree as ET
import requests
import os
from logger import get_logger

logger = get_logger("NET-SCANNER")
SETTINGS_FILE = "/opt/smart-light-guard/settings.json"
SCAN_INTERVAL = 300  # Alle 5 Minuten
DEFAULT_SUBNET = "192.168.1.0/24"  # Default if not provided or dynamically detected

def scan_network(subnet=DEFAULT_SUBNET):
    logger.info(f"Starte Netzwerkscan für: {subnet}")
    devices = []
    try:
        # nmap -sn (Ping Scan) mit XML Output
        result = subprocess.run(
            ["nmap", "-sn", "-oX", "-", subnet],
            capture_output=True, text=True, check=True
        )
        
        root = ET.fromstring(result.stdout)
        
        for host in root.findall('host'):
            status = host.find('status')
            if status is not None and status.get('state') == 'up':
                ip = ""
                mac = "Unknown"
                name = "Unknown"
                
                for address in host.findall('address'):
                    if address.get('addrtype') == 'ipv4':
                        ip = address.get('addr')
                    elif address.get('addrtype') == 'mac':
                        mac = address.get('addr')
                        
                hostnames = host.find('hostnames')
                if hostnames is not None:
                    hostname = hostnames.find('hostname')
                    if hostname is not None:
                        name = hostname.get('name', 'Unknown')
                        
                if ip:
                    devices.append({
                        "ip": ip,
                        "mac": mac,
                        "name": name
                    })
                    
        return devices
    except subprocess.CalledProcessError as e:
        logger.error(f"Nmap Fehler: {e}")
    except ET.ParseError as e:
        logger.error(f"XML Parse Fehler von nmap Output: {e}")
    except Exception as e:
        logger.error(f"Unerwarteter Fehler beim Scan: {e}")
        
    return devices

def upload_devices(devices):
    if not os.path.exists(SETTINGS_FILE):
        return
        
    try:
        with open(SETTINGS_FILE, "r") as f:
            settings = json.load(f)
    except Exception as e:
        logger.error(f"Fehler beim Lesen der settings.json: {e}")
        return
        
    backend = settings.get("backend", {})
    hub_id = backend.get("hub_id")
    api_key = backend.get("api_key")
    base_url = backend.get("base_url")

    if not hub_id or not api_key:
        logger.debug("Hub nicht registriert. Überspringe Upload.")
        return

    url = f"{base_url}/hubs/network-devices"
    headers = {
        "X-Hub-Api-Key": api_key,
        "Content-Type": "application/json"
    }
    
    payload = {
        "hub_id": hub_id,
        "devices": devices
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code in [200, 201]:
            logger.info(f"✅ {len(devices)} Netzwerkgeräte erfolgreich gemeldet.")
        else:
            logger.error(f"Backend-Fehler {response.status_code}: {response.text}")
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Netzwerkfehler beim Upload der Geräte: {e}")

if __name__ == "__main__":
    logger.info("🚀 Starte Network Scanner Agent...")
    while True:
        found_devices = scan_network(DEFAULT_SUBNET)
        if found_devices:
            upload_devices(found_devices)
        time.sleep(SCAN_INTERVAL)
