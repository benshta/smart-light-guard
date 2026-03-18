#!/bin/bash
# ==============================================================================
# Smart Light Guard - ULTIMATIVE AUTO-INSTALL (Headless Edition)
# ==============================================================================

if [ "$EUID" -ne 0 ]; then
  echo "❌ Bitte führe dieses Skript als root aus (sudo bash setup.sh)"
  exit
fi

echo "🚀 Starte System-Konfiguration (Headless Mode)..."

export DEBIAN_FRONTEND=noninteractive
apt update && apt upgrade -y
apt install -y avahi-daemon git wget curl gpg lsb-release

# deCONZ Headless Repository & Installation
wget -qO - http://phoscon.de/apt/deconz.pub.key | gpg --dearmor --yes -o /usr/share/keyrings/deconz-archive-keyring.gpg
CODENAME=$(lsb_release -cs)
echo "deb [signed-by=/usr/share/keyrings/deconz-archive-keyring.gpg] http://phoscon.de/apt/deconz $CODENAME main" | tee /etc/apt/sources.list.d/deconz.list

apt update
apt install -y deconz-headless python3-websocket python3-requests python3-flask

APP_DIR="/opt/smart-light-guard"
GIT_REPO="https://github.com/benshta/smart-light-guard.git"

mkdir -p $APP_DIR
if [ -d "$APP_DIR/.git" ]; then
    cd $APP_DIR && git pull origin main
else
    git clone $GIT_REPO $APP_DIR
fi

# Rechte-Fix für Benji
MAIN_USER="benji"
chown -R $MAIN_USER:$MAIN_USER $APP_DIR
chmod -R 775 $APP_DIR
chmod +x $APP_DIR/*.py

# Hardware-Fixes für RaspBee II
CONFIG_FILE="/boot/firmware/config.txt"
[ ! -f "$CONFIG_FILE" ] && CONFIG_FILE="/boot/config.txt"
sed -i '/^enable_uart/d' "$CONFIG_FILE"
sed -i '/^dtoverlay=disable-bt/d' "$CONFIG_FILE"
echo "enable_uart=1" >> "$CONFIG_FILE"
echo "dtoverlay=disable-bt" >> "$CONFIG_FILE"

# deCONZ Service Override (Trennung von API 8080 und WebSocket 8088)
mkdir -p /etc/systemd/system/deconz.service.d/
cat <<EOF > /etc/systemd/system/deconz.service.d/override.conf
[Service]
ExecStart=
ExecStart=/usr/bin/deCONZ -platform offscreen --http-port=8080 --ws-port=8088 --dev=/dev/ttyAMA0
EOF

create_slg_service() {
    cat <<EOF > /etc/systemd/system/$1.service
[Unit]
Description=$2
After=network.target deconz.service
[Service]
User=root
WorkingDirectory=$APP_DIR
ExecStart=/usr/bin/python3 $APP_DIR/$3
Restart=always
[Install]
WantedBy=multi-user.target
EOF
}

create_slg_service "slg-dashboard" "SLG Dashboard" "1_dashboard.py"
create_slg_service "slg-monitor" "SLG Monitor" "2_monitor.py"
create_slg_service "slg-cloud-sync" "SLG Cloud Sync" "3_cloud_sync.py"

systemctl daemon-reload
systemctl enable deconz slg-dashboard slg-monitor slg-cloud-sync
echo "✅ Setup abgeschlossen. Neustart in 5s..."
sleep 5
reboot