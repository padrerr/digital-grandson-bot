import logging

from app.db import Session, AuditLog

log = logging.getLogger(__name__)


async def log_action(user_id, family_id, action, payload=""):
    """Пишет действие в журнал аудита. Не падает при ошибке."""
    try:
        async with Session() as s:
            entry = AuditLog(
                user_id=user_id,
                family_id=family_id,
                action=action[:50],
                payload=(payload or "")[:500],
            )
            s.add(entry)
            await s.commit()
    except Exception as e:
        log.warning("audit log failed: %s", e)