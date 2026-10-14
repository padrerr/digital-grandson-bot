import logging
import os
from datetime import datetime

log = logging.getLogger(__name__)

HEARTBEAT_FILE = "data/heartbeat.txt"


def heartbeat():
    try:
        os.makedirs("data", exist_ok=True)
        with open(HEARTBEAT_FILE, "w", encoding="utf-8") as f:
            f.write(datetime.now().isoformat())
    except Exception as e:
        log.warning("heartbeat failed: %s", e)


def last_heartbeat():
    try:
        if not os.path.isfile(HEARTBEAT_FILE):
            return None
        with open(HEARTBEAT_FILE, "r", encoding="utf-8") as f:
            txt = f.read().strip()
        return datetime.fromisoformat(txt)
    except Exception:
        return None