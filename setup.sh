#!/bin/bash
# ==============================================================================
# Smart Light Guard - ULTIMATIVE AUTO-INSTALL 
# ==============================================================================

if [ "$EUID" -ne 0 ]; then
  echo "❌ Bitte führe dieses Skript als root aus (sudo bash setup.sh)"
  exit
fi

echo "🚀 Starte vollautomatische System-Konfiguration für Smart Light Guard..."

export DEBIAN_FRONTEND=noninteractive
apt update && apt upgrade -y
apt install -y avahi-daemon git wget curl gpg lsb-release

# deCONZ Repository
wget -qO - http://phoscon.de/apt/deconz.pub.key | gpg --dearmor --yes -o /usr/share/keyrings/deconz-archive-keyring.gpg
CODENAME=$(lsb_release -cs)
echo "deb [signed-by=/usr/share/keyrings/deconz-archive-keyring.gpg] http://phoscon.de/apt/deconz $CODENAME main" | tee /etc/apt/sources.list.d/deconz.list

apt update
apt install -y deconz python3-websocket python3-requests python3-flask

# ==============================================================================
# CODE AUS DEM GIT REPOSITORY LADEN
# ==============================================================================
APP_DIR="/opt/smart-light-guard"
GIT_REPO="https://github.com/benshta/smart-light-guard.git"

echo "📥 Lade neuesten Code aus dem Git-Repository..."
mkdir -p $APP_DIR

if [ -d "$APP_DIR/.git" ]; then
    cd $APP_DIR && git pull origin main
else
    git clone $GIT_REPO $APP_DIR
fi
chmod +x $APP_DIR/*.py

# ==============================================================================
# HARDWARE-FIXES FÜR RASPBEE II
# ==============================================================================
echo "⚙️ Konfiguriere Hardware-Schnittstellen (I2C & UART)..."
CONFIG_FILE="/boot/firmware/config.txt"
[ ! -f "$CONFIG_FILE" ] && CONFIG_FILE="/boot/config.txt"
CMD_FILE="/boot/firmware/cmdline.txt"
[ ! -f "$CMD_FILE" ] && CMD_FILE="/boot/cmdline.txt"

sed -i '/^enable_uart/d' "$CONFIG_FILE"
sed -i '/^dtoverlay=disable-bt/d' "$CONFIG_FILE"
sed -i '/^dtparam=i2c_arm/d' "$CONFIG_FILE"
sed -i '/^dtparam=i2c_vc/d' "$CONFIG_FILE"

echo "enable_uart=1" >> "$CONFIG_FILE"
echo "dtoverlay=disable-bt" >> "$CONFIG_FILE"
echo "dtparam=i2c_arm=on" >> "$CONFIG_FILE"
echo "dtparam=i2c_vc=on" >> "$CONFIG_FILE"

sed -i 's/console=serial0,115200 //g' "$CMD_FILE"
sed -i 's/console=ttyAMA0,115200 //g' "$CMD_FILE"

systemctl stop serial-getty@ttyAMA0.service 2>/dev/null
systemctl disable serial-getty@ttyAMA0.service 2>/dev/null
systemctl mask serial-getty@ttyAMA0.service 2>/dev/null

MAIN_USER=${SUDO_USER:-pi}
usermod -a -G dialout,tty,i2c $MAIN_USER

# ==============================================================================
# SYSTEMD SERVICES & OVERRIDES
# ==============================================================================
echo "⚙️ Richte Systemd-Dienste ein..."
mkdir -p /etc/systemd/system/deconz.service.d/
cat <<EOF > /etc/systemd/system/deconz.service.d/override.conf
[Service]
ExecStart=
ExecStart=/usr/bin/deCONZ -platform minimal --http-port=8080 --dev=/dev/ttyAMA0
EOF

create_slg_service() {
    local SERVICE_NAME=$1
    local DESCRIPTION=$2
    local SCRIPT_NAME=$3
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

systemctl daemon-reload
systemctl enable deconz.service
systemctl enable slg-dashboard.service slg-monitor.service slg-cloud-sync.service

echo "✅ Setup erfolgreich abgeschlossen! Das System startet in 5 Sekunden neu..."
sleep 5
reboot