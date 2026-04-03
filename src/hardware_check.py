import os
import sys
from logger import get_logger

logger = get_logger("HARDWARE-CHECK")

def check_hardware():
    # deCONZ default serial device on Pi for RaspBee II
    device_path = "/dev/ttyAMA0"
    
    if not os.path.exists(device_path):
        logger.critical(f"Kritischer Fehler: Zigbee-Antenne (Device {device_path}) nicht gefunden!")
        sys.exit(1)
        
    if not os.access(device_path, os.W_OK | os.R_OK):
        logger.critical(f"Kritischer Fehler: Keine Lese-/Schreibrechte für Device {device_path}!")
        sys.exit(1)
        
    logger.info(f"Hardware-Check erfolgreich. Device {device_path} ist einsatzbereit.")
    sys.exit(0)

if __name__ == "__main__":
    check_hardware()
