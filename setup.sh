#!/bin/bash
# ==============================================================================
# Smart Light Guard - ULTIMATIVE AUTO-INSTALL (Universal 32/64-bit)
# Inkl. RaspBee II Hardware-Fixes (I2C, UART, Bluetooth, Port-Binding)
# ==============================================================================

if [ "$EUID" -ne 0 ]; then
  echo "❌ Bitte führe dieses Skript als root aus (sudo ./setup.sh)"
  exit
fi

echo "🚀 Starte vollautomatische System-Konfiguration für Smart Light Guard..."

# 1. System-Vorbereitung (Non-Interactive verhindert Rückfragen)
export DEBIAN_FRONTEND=noninteractive
apt update && apt upgrade -y
apt install -y avahi-daemon git wget curl gpg lsb-release

# 2. deCONZ (Phoscon) Repository intelligent einrichten
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
apt install -y deconz python3-websocket python3-requests python3-flask

# ==============================================================================
# 4. HARDWARE-FIXES FÜR RASPBEE II (Das Herzstück)
# ==============================================================================
echo "⚙️ Konfiguriere Hardware-Schnittstellen (I2C & UART)..."

CONFIG_FILE="/boot/firmware/config.txt"
[ ! -f "$CONFIG_FILE" ] && CONFIG_FILE="/boot/config.txt"

CMD_FILE="/boot/firmware/cmdline.txt"
[ ! -f "$CMD_FILE" ] && CMD_FILE="/boot/cmdline.txt"

# 4.1. Altlasten bereinigen
sed -i '/^enable_uart/d' "$CONFIG_FILE"
sed -i '/^dtoverlay=disable-bt/d' "$CONFIG_FILE"
sed -i '/^dtparam=i2c_arm/d' "$CONFIG_FILE"
sed -i '/^dtparam=i2c_vc/d' "$CONFIG_FILE"

# 4.2. Bluetooth deaktivieren, UART & I2C (für die RTC) aktivieren
echo "enable_uart=1" >> "$CONFIG_FILE"
echo "dtoverlay=disable-bt" >> "$CONFIG_FILE"
echo "dtparam=i2c_arm=on" >> "$CONFIG_FILE"
echo "dtparam=i2c_vc=on" >> "$CONFIG_FILE"

# 4.3. Linux-Konsole von der Antenne verbannen
sed -i 's/console=serial0,115200 //g' "$CMD_FILE"
sed -i 's/console=ttyAMA0,115200 //g' "$CMD_FILE"

# 4.4. Störenden Terminal-Dienst rigoros killen
systemctl stop serial-getty@ttyAMA0.service 2>/dev/null
systemctl disable serial-getty@ttyAMA0.service 2>/dev/null
systemctl mask serial-getty@ttyAMA0.service 2>/dev/null

# 4.5. Berechtigungen für den aktuellen User setzen (damit das Dashboard funken darf)
MAIN_USER=${SUDO_USER:-pi}
usermod -a -G dialout,tty,i2c $MAIN_USER

# ==============================================================================
# 5. SYSTEMD SERVICES & OVERRIDES
# ==============================================================================
echo "⚙️ Richte Systemd-Dienste ein..."

# 5.1. deCONZ zwingen, auf Port 8080 und ttyAMA0 zu laufen (Update-sicher!)
mkdir -p /etc/systemd/system/deconz.service.d/
cat <<EOF > /etc/systemd/system/deconz.service.d/override.conf
[Service]
ExecStart=
ExecStart=/usr/bin/deCONZ -platform minimal --http-port=8080 --dev=/dev/ttyAMA0
EOF

APP_DIR="/opt/smart-light-guard"

# 5.2. Hilfsfunktion zum Erstellen der SLG-Service-Files
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

# ==============================================================================
# 6. ABSCHLUSS & NEUSTART
# ==============================================================================
echo "⚙️ Aktiviere Dienste..."
systemctl daemon-reload
systemctl unmask deconz.service || true

# Dienste für den Autostart aktivieren
systemctl enable deconz.service
systemctl enable slg-dashboard.service slg-monitor.service slg-cloud-sync.service



echo "✅ Setup erfolgreich abgeschlossen!"
echo "🔄 Das System hat alle Hardware-Fixes angewendet und startet in 5 Sekunden neu..."
sleep 5
reboot