import logging
import os
import shutil
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

BACKUP_DIR = "backups"
DB_PATH = "data/bot.db"
KEEP_DAYS = 30


def make_backup():
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        if not os.path.isfile(DB_PATH):
            log.warning("DB file not found: %s", DB_PATH)
            return None
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        target = os.path.join(BACKUP_DIR, "bot_" + stamp + ".db")
        shutil.copy2(DB_PATH, target)
        log.info("Backup created: %s", target)
        _cleanup_old()
        return target
    except Exception as e:
        log.warning("Backup failed: %s", e)
        return None


def _cleanup_old():
    try:
        if not os.path.isdir(BACKUP_DIR):
            return
        cutoff = datetime.now() - timedelta(days=KEEP_DAYS)
        for name in os.listdir(BACKUP_DIR):
            if not name.startswith("bot_") or not name.endswith(".db"):
                continue
            path = os.path.join(BACKUP_DIR, name)
            mtime = datetime.fromtimestamp(os.path.getmtime(path))
            if mtime < cutoff:
                os.remove(path)
                log.info("Removed old backup: %s", name)
    except Exception as e:
        log.warning("Backup cleanup failed: %s", e)


def list_backups():
    if not os.path.isdir(BACKUP_DIR):
        return []
    items = []
    for name in sorted(os.listdir(BACKUP_DIR), reverse=True):
        if name.startswith("bot_") and name.endswith(".db"):
            path = os.path.join(BACKUP_DIR, name)
            size = os.path.getsize(path)
            mtime = datetime.fromtimestamp(os.path.getmtime(path))
            items.append({
                "name": name,
                "path": path,
                "size_kb": round(size / 1024, 1),
                "date": mtime,
            })
    return items