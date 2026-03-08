#!/bin/bash
# ==============================================================================
# Smart Light Guard - ULTIMATIVE AUTO-INSTALL (Universal 32/64-bit)
# ==============================================================================

echo "🚀 Starte vollautomatische System-Konfiguration für Smart Light Guard..."

# 1. System-Vorbereitung (Non-Interactive verhindert Rückfragen)
export DEBIAN_FRONTEND=noninteractive
apt update && apt upgrade -y
apt install -y avahi-daemon git wget curl gpg lsb-release

# 2. deCONZ (Phoscon) Repository intelligent einrichten
# Erkennt automatisch 32-bit (Raspbian) vs 64-bit (Debian/Ubuntu)
wget -qO - http://phoscon.de/apt/deconz.pub.key | gpg --dearmor --yes -o /usr/share/keyrings/deconz-archive-keyring.gpg

ARCH=$(uname -m)
CODENAME=$(lsb_release -cs)

if [[ "$ARCH" == "armv7l" ]]; then
    # 32-bit Architektur (Optimiert für Pi Zero 2W / Pi 3)
    REPO_URL="http://phoscon.de/apt/deconz $CODENAME main"
else
    # 64-bit Architektur (Aarch64 / Pi 4 / Pi 5)
    REPO_URL="http://phoscon.de/apt/deconz $CODENAME main"
fi

echo "deb [signed-by=/usr/share/keyrings/deconz-archive-keyring.gpg] $REPO_URL" | tee /etc/apt/sources.list.d/deconz.list

# 3. Installation der Pakete
apt update
# Wir installieren 'deconz', das deckt meist beide Versionen ab
apt install -y deconz python3-websocket python3-requests python3-flask

# 4. Port-Fix: deCONZ von 80 auf 8080 (Regex verhindert 808080-Fehler)
SERVICE_FILE="/lib/systemd/system/deconz.service"
if [ -f "$SERVICE_FILE" ]; then
    echo "⚙️ Setze deCONZ Port auf 8080..."
    sed -i -E 's/--http-port=[0-9]+/--http-port=8080/g' "$SERVICE_FILE"
fi

# 5. Hardware UART/Bluetooth Konfiguration für RaspBee II
# Deaktiviert Bluetooth auf der seriellen Schnittstelle für stabilere Zigbee-Verbindung
CONFIG_FILE="/boot/firmware/config.txt"
[ ! -f "$CONFIG_FILE" ] && CONFIG_FILE="/boot/config.txt"

if ! grep -q "dtoverlay=disable-bt" "$CONFIG_FILE"; then
  echo "dtoverlay=disable-bt" >> "$CONFIG_FILE"
  echo "enable_uart=1" >> "$CONFIG_FILE"
fi
systemctl disable serial-getty@ttyAMA0.service || true

# 6. SYSTEMD SERVICES ERSTELLEN
APP_DIR="/opt/smart-light-guard"

# Hilfsfunktion zum Erstellen der Service-Files
create_slg_service() {
    local SERVICE_NAME=$1
    local DESCRIPTION=$2
    local SCRIPT_NAME=$3
    
    echo "⚙️ Erstelle Service: $SERVICE_NAME..."
    cat <<EOF > /etc/systemd/system/$SERVICE_NAME.service
[Unit]
Description=$DESCRIPTION
After=network.target deconz.service
Wants=deconz.service

[Service]
User=root
WorkingDirectory=$APP_DIR
ExecStart=/usr/bin/python3 $APP_DIR/$SCRIPT_NAME
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
}

create_slg_service "slg-dashboard" "SLG Web Dashboard" "1_dashboard.py"
create_slg_service "slg-monitor" "SLG Zigbee Monitor" "2_monitor.py"
create_slg_service "slg-cloud-sync" "SLG Cloud Sync Agent" "3_cloud_sync.py"

# 7. Dienste aktivieren und starten
echo "⚙️ Aktiviere Dienste..."
systemctl daemon-reload
systemctl unmask deconz.service || true

# Wir versuchen beide Service-Namen zu aktivieren (Sicherheits-Fallback)
systemctl enable deconz.service || systemctl enable deconz-headless.service
systemctl enable slg-dashboard.service slg-monitor.service slg-cloud-sync.service

echo "✅ Setup erfolgreich abgeschlossen!"
echo "🔄 Das System wird in 5 Sekunden neu gestartet..."
sleep 5
reboot