#!/bin/bash
# ==============================================================================
# Smart Light Guard - Microservice Provisioning Script
# ==============================================================================

echo "🚀 Starte vollautomatisches Setup (Microservice-Edition)..."

# 1. System Update & Hostname (für .local Erreichbarkeit)
hostnamectl set-hostname smart-light-guard-poc
apt update && apt upgrade -y
apt install avahi-daemon -y

# 2. deCONZ (Phoscon) Gateway installieren
wget -O - http://phoscon.de/apt/deconz.pub.key | gpg --dearmor -o /usr/share/keyrings/deconz-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/deconz-archive-keyring.gpg] http://phoscon.de/apt/deconz bookworm main" | tee /etc/apt/sources.list.d/deconz.list
apt update
apt install deconz-headless -y

# 3. deCONZ auf Port 8080 verschieben
sed -i 's/--http-port=80/--http-port=8080/g' /lib/systemd/system/deconz.service

# 4. Python-Umgebung einrichten
apt install python3-websocket python3-requests python3-flask -y

# 5. Hardware UART/Bluetooth für RaspBee II konfigurieren
if ! grep -q "dtoverlay=disable-bt" /boot/firmware/config.txt; then
  echo "dtoverlay=disable-bt" >> /boot/firmware/config.txt
  echo "enable_uart=1" >> /boot/firmware/config.txt
fi
systemctl disable serial-getty@ttyAMA0.service

# 6. Applikations-Verzeichnis erstellen und Module herunterladen
echo "📥 Lade Microservices aus dem GitHub-Repo herunter..."
APP_DIR="/opt/smart-light-guard"
mkdir -p $APP_DIR

REPO_URL="https://raw.githubusercontent.com/benshta/smart-light-guard/main"

wget -O $APP_DIR/1_dashboard.py $REPO_URL/1_dashboard.py
wget -O $APP_DIR/2_monitor.py $REPO_URL/2_monitor.py
wget -O $APP_DIR/3_cloud_sync.py $REPO_URL/3_cloud_sync.py
wget -O $APP_DIR/4_alert_handler.py $REPO_URL/4_alert_handler.py

# ==============================================================================
# 7. SYSTEMD SERVICES ERSTELLEN
# ==============================================================================

echo "⚙️ Richte Systemd-Dienste ein..."

cat <<EOF > /etc/systemd/system/slg-dashboard.service
[Unit]
Description=SLG Web Dashboard
After=network.target
[Service]
User=root
WorkingDirectory=$APP_DIR
ExecStart=/usr/bin/python3 $APP_DIR/1_dashboard.py
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF

cat <<EOF > /etc/systemd/system/slg-monitor.service
[Unit]
Description=SLG Zigbee Monitor
After=deconz.service
Wants=deconz.service
[Service]
User=root
WorkingDirectory=$APP_DIR
ExecStart=/usr/bin/python3 $APP_DIR/2_monitor.py
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF

cat <<EOF > /etc/systemd/system/slg-cloud-sync.service
[Unit]
Description=SLG Cloud Sync Agent
After=network.target
[Service]
User=root
WorkingDirectory=$APP_DIR
ExecStart=/usr/bin/python3 $APP_DIR/3_cloud_sync.py
Restart=always
RestartSec=10
[Install]
WantedBy=multi-user.target
EOF

# ==============================================================================
# 8. Setup abschließen
# ==============================================================================

systemctl daemon-reload
systemctl enable deconz slg-dashboard slg-monitor slg-cloud-sync

echo "✅ Installation erfolgreich! Alle 3 Microservices sind konfiguriert."
echo "🔄 Das System startet in 5 Sekunden neu..."
sleep 5
reboot