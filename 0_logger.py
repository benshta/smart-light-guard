import logging
import os
from logging.handlers import RotatingFileHandler

LOG_FILE = "/opt/smart-light-guard/system.log"

def get_logger(name):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    # Verhindert, dass Handler mehrfach hinzugefügt werden
    if not logger.handlers:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        # Maximal 2 MB pro Datei, behält die letzten 2 Backups
        handler = RotatingFileHandler(LOG_FILE, maxBytes=2*1024*1024, backupCount=2)
        formatter = logging.Formatter('[%(asctime)s] [%(name)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
    return logger