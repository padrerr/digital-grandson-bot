import secrets
import logging
import json
from datetime import datetime, date, timedelta
from sqlalchemy import (
    BigInteger, String, Integer, Boolean, DateTime, ForeignKey,
    select, and_, text,
)
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import settings

log = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100), default="")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    consent: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Family(Base):
    __tablename__ = "families"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), default="")
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class FamilyMember(Base):
    __tablename__ = "family_members"
    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    role: Mapped[str] = mapped_column(String(20), default="member")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Elderly(Base):
    __tablename__ = "elderly"
    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(100))
    invite_code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    wake_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    wake_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    checkin_hour: Mapped[int] = mapped_column(Integer, default=10)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    quiet_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    quiet_start: Mapped[int] = mapped_column(Integer, default=23)
    quiet_end: Mapped[int] = mapped_column(Integer, default=7)
    birthday: Mapped[str | None] = mapped_column(String(5), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Routine(Base):
    __tablename__ = "routines"
    id: Mapped[int] = mapped_column(primary_key=True)
    elderly_id: Mapped[int] = mapped_column(ForeignKey("elderly.id"))
    title: Mapped[str] = mapped_column(String(100))
    mode: Mapped[str] = mapped_column(String(20), default="wake_offset")
    offset_min: Mapped[int] = mapped_column(Integer, default=0)
    hour: Mapped[int] = mapped_column(Integer, default=8)
    minute: Mapped[int] = mapped_column(Integer, default=0)
    measure_kind: Mapped[str | None] = mapped_column(String(20), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(primary_key=True)
    elderly_id: Mapped[int] = mapped_column(ForeignKey("elderly.id"))
    routine_id: Mapped[int | None] = mapped_column(ForeignKey("routines.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    note: Mapped[str] = mapped_column(String(1000), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Measurement(Base):
    __tablename__ = "measurements"
    id: Mapped[int] = mapped_column(primary_key=True)
    elderly_id: Mapped[int] = mapped_column(ForeignKey("elderly.id"))
    event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(20))
    value: Mapped[str] = mapped_column(String(50))
    note: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WellbeingLog(Base):
    __tablename__ = "wellbeing_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    elderly_id: Mapped[int] = mapped_column(ForeignKey("elderly.id"))
    text: Mapped[str] = mapped_column(String(1000))
    category: Mapped[str] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(String(20), default="text")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class HelpRequest(Base):
    __tablename__ = "help_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    family_id: Mapped[int | None] = mapped_column(ForeignKey("families.id"), nullable=True)
    request_text: Mapped[str] = mapped_column(String(2000))
    reply_text: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="new")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    replied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CustomTemplate(Base):
    __tablename__ = "custom_templates"
    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"))
    name: Mapped[str] = mapped_column(String(100))
    items_json: Mapped[str] = mapped_column(String(8000))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    family_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(50))
    payload: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AlertAck(Base):
    __tablename__ = "alert_acks"
    id: Mapped[int] = mapped_column(primary_key=True)
    elderly_id: Mapped[int] = mapped_column(Integer)
    user_id: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(30))
    summary: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class UserMute(Base):
    __tablename__ = "user_mutes"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    until_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Note(Base):
    __tablename__ = "notes"
    id: Mapped[int] = mapped_column(primary_key=True)
    elderly_id: Mapped[int] = mapped_column(ForeignKey("elderly.id"))
    text: Mapped[str] = mapped_column(String(200))
    remind_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    feedback: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


engine = create_async_engine(settings.DB_URL, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)


async def _migrate():
    async with engine.begin() as conn:
        try:
            r = await conn.execute(text("PRAGMA table_info(elderly)"))
            cols = {row[1] for row in r.fetchall()}
            if cols:
                if "quiet_enabled" not in cols:
                    await conn.execute(text(
                        "ALTER TABLE elderly ADD COLUMN quiet_enabled INTEGER DEFAULT 0"
                    ))
                if "quiet_start" not in cols:
                    await conn.execute(text(
                        "ALTER TABLE elderly ADD COLUMN quiet_start INTEGER DEFAULT 23"
                    ))
                if "quiet_end" not in cols:
                    await conn.execute(text(
                        "ALTER TABLE elderly ADD COLUMN quiet_end INTEGER DEFAULT 7"
                    ))
                if "birthday" not in cols:
                    await conn.execute(text(
                        "ALTER TABLE elderly ADD COLUMN birthday TEXT"
                    ))
            r2 = await conn.execute(text("PRAGMA table_info(routines)"))
            rcols = {row[1] for row in r2.fetchall()}
            if rcols and "measure_kind" not in rcols:
                await conn.execute(text(
                    "ALTER TABLE routines ADD COLUMN measure_kind TEXT"
                ))
        except Exception as e:
            log.warning("Migration failed: %s", e)


async def _cleanup_duplicates():
    """Чистит дубликаты в family_members — оставляет самую раннюю запись."""
    try:
        async with engine.begin() as conn:
            r = await conn.execute(text(
                "SELECT user_id, COUNT(*) as c FROM family_members "
                "GROUP BY user_id HAVING c > 1"
            ))
            dup_users = [row[0] for row in r.fetchall()]
            for uid in dup_users:
                r2 = await conn.execute(text(
                    "SELECT id FROM family_members WHERE user_id = :uid "
                    "ORDER BY id ASC"
                ), {"uid": uid})
                ids = [row[0] for row in r2.fetchall()]
                keep = ids[0]
                to_delete = ids[1:]
                for x in to_delete:
                    await conn.execute(text(
                        "DELETE FROM family_members WHERE id = :x"
                    ), {"x": x})
                log.info(
                    "Cleaned duplicate family_members for user %s: "
                    "kept %s, removed %s", uid, keep, to_delete,
                )
    except Exception as e:
        log.warning("Cleanup duplicates failed: %s", e)


async def init_db():
    import os
    os.makedirs("data", exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _migrate()
    await _cleanup_duplicates()


def new_code() -> str:
    return secrets.token_urlsafe(8)


# ============================================================
# USERS
# ============================================================

async def get_user_by_tg(tg_id: int) -> User | None:
    async with Session() as s:
        r = await s.execute(select(User).where(User.tg_id == tg_id))
        u = r.scalars().first()
        if u and tg_id in settings.admin_ids and not u.is_admin:
            u.is_admin = True
            await s.commit()
            await s.refresh(u)
        return u


async def get_user(uid: int) -> User | None:
    async with Session() as s:
        return await s.get(User, uid)


async def create_user(tg_id: int, name: str) -> User:
    async with Session() as s:
        u = User(tg_id=tg_id, name=name, consent=True,
                 consent_at=datetime.now(),
                 is_admin=(tg_id in settings.admin_ids))
        s.add(u)
        await s.commit()
        await s.refresh(u)
        return u


async def list_admins() -> list[User]:
    async with Session() as s:
        r = await s.execute(select(User).where(User.is_admin == True))
        return list(r.scalars().all())


async def delete_user_everything(uid: int) -> dict:
    info = {"was_owner": False, "transferred_to": None, "family_deleted": False}
    from sqlalchemy import delete as sqldel
    async with Session() as s:
        u = await s.get(User, uid)
        if not u:
            return info

        r = await s.execute(select(Elderly).where(Elderly.user_id == uid))
        eld = r.scalars().first()
        if eld:
            await s.execute(sqldel(Routine).where(Routine.elderly_id == eld.id))
            await s.execute(sqldel(Event).where(Event.elderly_id == eld.id))
            await s.execute(sqldel(WellbeingLog).where(WellbeingLog.elderly_id == eld.id))
            await s.execute(sqldel(Measurement).where(Measurement.elderly_id == eld.id))
            await s.execute(sqldel(Note).where(Note.elderly_id == eld.id))
            await s.execute(sqldel(AlertAck).where(AlertAck.elderly_id == eld.id))
            await s.delete(eld)

        r = await s.execute(select(FamilyMember).where(FamilyMember.user_id == uid))
        members = list(r.scalars().all())
        for m in members:
            f = await s.get(Family, m.family_id)
            if f and f.owner_user_id == uid:
                info["was_owner"] = True
                r2 = await s.execute(
                    select(FamilyMember).where(
                        and_(FamilyMember.family_id == m.family_id,
                             FamilyMember.user_id != uid)
                    )
                )
                others = list(r2.scalars().all())
                if others:
                    new_owner = others[0]
                    f.owner_user_id = new_owner.user_id
                    new_owner.role = "owner"
                    info["transferred_to"] = new_owner.user_id
                else:
                    r3 = await s.execute(
                        select(Elderly).where(Elderly.family_id == m.family_id)
                    )
                    for e in r3.scalars().all():
                        await s.execute(sqldel(Routine).where(Routine.elderly_id == e.id))
                        await s.execute(sqldel(Event).where(Event.elderly_id == e.id))
                        await s.execute(sqldel(WellbeingLog).where(WellbeingLog.elderly_id == e.id))
                        await s.execute(sqldel(Measurement).where(Measurement.elderly_id == e.id))
                        await s.execute(sqldel(Note).where(Note.elderly_id == e.id))
                        await s.execute(sqldel(AlertAck).where(AlertAck.elderly_id == e.id))
                        await s.delete(e)
                    await s.execute(sqldel(CustomTemplate).where(CustomTemplate.family_id == m.family_id))
                    await s.delete(f)
                    info["family_deleted"] = True
            await s.delete(m)

        await s.delete(u)
        await s.commit()
    return info


# ============================================================
# FAMILIES
# ============================================================

async def create_family(owner: User, name: str) -> Family:
    async with Session() as s:
        f = Family(name=name, owner_user_id=owner.id)
        s.add(f)
        await s.commit()
        await s.refresh(f)
        m = FamilyMember(family_id=f.id, user_id=owner.id, role="owner")
        s.add(m)
        await s.commit()
        return f


async def get_family(fid: int) -> Family | None:
    async with Session() as s:
        return await s.get(Family, fid)


async def get_user_family(uid: int):
    """Возвращает первую найденную семью пользователя. Не падает при дублях."""
    async with Session() as s:
        r = await s.execute(
            select(FamilyMember).where(FamilyMember.user_id == uid)
            .order_by(FamilyMember.id.asc())
        )
        m = r.scalars().first()
        if not m:
            return None
        f = await s.get(Family, m.family_id)
        return (f, m.role) if f else None


async def add_family_member(family_id: int, user_id: int, role: str = "member"):
    async with Session() as s:
        # защита от дублей
        r = await s.execute(select(FamilyMember).where(
            and_(FamilyMember.family_id == family_id,
                 FamilyMember.user_id == user_id)
        ))
        existing = r.scalars().first()
        if existing:
            return
        s.add(FamilyMember(family_id=family_id, user_id=user_id, role=role))
        await s.commit()


async def remove_family_member(family_id: int, user_id: int):
    async with Session() as s:
        r = await s.execute(select(FamilyMember).where(
            and_(FamilyMember.family_id == family_id, FamilyMember.user_id == user_id)
        ))
        m = r.scalar_one_or_none()
        if m and m.role != "owner":
            await s.delete(m)
            await s.commit()
            return True
    return False


async def list_family_members(family_id: int):
    async with Session() as s:
        r = await s.execute(
            select(FamilyMember).where(FamilyMember.family_id == family_id)
        )
        out = []
        for m in r.scalars().all():
            u = await s.get(User, m.user_id)
            if u:
                out.append((u, m.role))
        return out


async def list_all_families() -> list[Family]:
    async with Session() as s:
        r = await s.execute(select(Family))
        return list(r.scalars().all())


async def count_family_members(family_id: int) -> int:
    async with Session() as s:
        r = await s.execute(select(FamilyMember).where(
            FamilyMember.family_id == family_id
        ))
        return len(list(r.scalars().all()))


async def count_family_elderly(family_id: int) -> int:
    async with Session() as s:
        r = await s.execute(select(Elderly).where(
            Elderly.family_id == family_id
        ))
        return len(list(r.scalars().all()))


async def get_member_role(family_id: int, user_id: int):
    async with Session() as s:
        r = await s.execute(select(FamilyMember).where(
            and_(FamilyMember.family_id == family_id,
                 FamilyMember.user_id == user_id)
        ))
        m = r.scalars().first()
        return m.role if m else None


async def set_member_role(family_id: int, user_id: int, role: str) -> bool:
    if role not in ("moderator", "member"):
        return False
    async with Session() as s:
        r = await s.execute(select(FamilyMember).where(
            and_(FamilyMember.family_id == family_id,
                 FamilyMember.user_id == user_id)
        ))
        m = r.scalars().first()
        if not m or m.role == "owner":
            return False
        m.role = role
        await s.commit()
    return True


async def can_edit_family_data(family_id: int, user_id: int) -> bool:
    role = await get_member_role(family_id, user_id)
    return role in ("owner", "moderator")


async def is_owner(family_id: int, user_id: int) -> bool:
    role = await get_member_role(family_id, user_id)
    return role == "owner"


# ============================================================
# ELDERLY
# ============================================================

async def add_elderly(family_id: int, name: str) -> Elderly:
    async with Session() as s:
        e = Elderly(family_id=family_id, name=name, invite_code=new_code())
        s.add(e)
        await s.commit()
        await s.refresh(e)
        return e


async def get_elderly(eid: int) -> Elderly | None:
    async with Session() as s:
        return await s.get(Elderly, eid)


async def get_elderly_by_code(code: str) -> Elderly | None:
    async with Session() as s:
        r = await s.execute(select(Elderly).where(Elderly.invite_code == code))
        return r.scalars().first()


async def get_elderly_by_user(uid: int) -> Elderly | None:
    """Возвращает первого привязанного близкого. Не падает при дублях."""
    async with Session() as s:
        r = await s.execute(
            select(Elderly).where(Elderly.user_id == uid)
            .order_by(Elderly.id.asc())
        )
        return r.scalars().first()


async def list_family_elderly(family_id: int) -> list[Elderly]:
    async with Session() as s:
        r = await s.execute(select(Elderly).where(Elderly.family_id == family_id))
        return list(r.scalars().all())


async def list_all_elderly() -> list[Elderly]:
    async with Session() as s:
        r = await s.execute(select(Elderly))
        return list(r.scalars().all())


async def link_elderly_user(elderly_id: int, user_id: int):
    async with Session() as s:
        e = await s.get(Elderly, elderly_id)
        if e:
            e.user_id = user_id
            await s.commit()


async def unlink_elderly_user(elderly_id: int):
    async with Session() as s:
        e = await s.get(Elderly, elderly_id)
        if e:
            e.user_id = None
            await s.commit()


async def set_wake(elderly_id: int):
    async with Session() as s:
        e = await s.get(Elderly, elderly_id)
        if e:
            e.wake_date = date.today().isoformat()
            e.wake_at = datetime.now()
            await s.commit()


async def clear_wake(elderly_id: int):
    async with Session() as s:
        e = await s.get(Elderly, elderly_id)
        if e:
            e.wake_date = None
            e.wake_at = None
            await s.commit()


async def set_quiet(elderly_id: int, enabled=None, start=None, end=None):
    async with Session() as s:
        e = await s.get(Elderly, elderly_id)
        if not e:
            return
        if enabled is not None:
            e.quiet_enabled = enabled
        if start is not None:
            e.quiet_start = start
        if end is not None:
            e.quiet_end = end
        await s.commit()


async def set_birthday(elderly_id: int, mm_dd):
    async with Session() as s:
        e = await s.get(Elderly, elderly_id)
        if e:
            e.birthday = mm_dd
            await s.commit()


async def list_elderly_with_birthday(mm_dd: str) -> list[Elderly]:
    async with Session() as s:
        r = await s.execute(select(Elderly).where(Elderly.birthday == mm_dd))
        return list(r.scalars().all())


def is_quiet_hours(e: Elderly, now: datetime) -> bool:
    if not e or not e.quiet_enabled:
        return False
    h = now.hour
    s, en = e.quiet_start, e.quiet_end
    if s == en:
        return False
    if s < en:
        return s <= h < en
    return h >= s or h < en


# ============================================================
# ROUTINES
# ============================================================

async def add_routine(elderly_id: int, title: str, mode: str,
                      offset_min: int = 0, hour: int = 8, minute: int = 0,
                      measure_kind=None) -> Routine:
    async with Session() as s:
        r = Routine(elderly_id=elderly_id, title=title, mode=mode,
                    offset_min=offset_min, hour=hour, minute=minute,
                    measure_kind=measure_kind)
        s.add(r)
        await s.commit()
        await s.refresh(r)
        return r


async def get_routines(elderly_id: int) -> list[Routine]:
    async with Session() as s:
        r = await s.execute(select(Routine).where(
            and_(Routine.elderly_id == elderly_id, Routine.active == True)
        ).order_by(Routine.offset_min, Routine.hour, Routine.minute))
        return list(r.scalars().all())


async def get_routine(rid: int) -> Routine | None:
    async with Session() as s:
        return await s.get(Routine, rid)


async def update_routine(rid: int, **kwargs):
    async with Session() as s:
        r = await s.get(Routine, rid)
        if r:
            for k, v in kwargs.items():
                setattr(r, k, v)
            await s.commit()


async def delete_routine(rid: int):
    async with Session() as s:
        r = await s.get(Routine, rid)
        if r:
            await s.delete(r)
            await s.commit()


async def delete_all_routines(elderly_id: int):
    async with Session() as s:
        r = await s.execute(select(Routine).where(Routine.elderly_id == elderly_id))
        for x in r.scalars().all():
            await s.delete(x)
        await s.commit()


# ============================================================
# CUSTOM TEMPLATES
# ============================================================

async def create_custom_template(family_id: int, name: str, items: list) -> CustomTemplate:
    async with Session() as s:
        t = CustomTemplate(
            family_id=family_id,
            name=name,
            items_json=json.dumps(items, ensure_ascii=False),
        )
        s.add(t)
        await s.commit()
        await s.refresh(t)
        return t


async def list_custom_templates(family_id: int) -> list[CustomTemplate]:
    async with Session() as s:
        r = await s.execute(select(CustomTemplate).where(
            CustomTemplate.family_id == family_id
        ).order_by(CustomTemplate.created_at.desc()))
        return list(r.scalars().all())


async def get_custom_template(tid: int) -> CustomTemplate | None:
    async with Session() as s:
        return await s.get(CustomTemplate, tid)


async def delete_custom_template(tid: int):
    async with Session() as s:
        t = await s.get(CustomTemplate, tid)
        if t:
            await s.delete(t)
            await s.commit()


def custom_template_items(t: CustomTemplate) -> list:
    try:
        return json.loads(t.items_json)
    except Exception:
        return []


# ============================================================
# EVENTS
# ============================================================

async def create_event(elderly_id: int, kind: str, routine_id=None) -> Event:
    async with Session() as s:
        e = Event(elderly_id=elderly_id, kind=kind, routine_id=routine_id)
        s.add(e)
        await s.commit()
        await s.refresh(e)
        return e


async def get_event(eid: int) -> Event | None:
    async with Session() as s:
        return await s.get(Event, eid)


async def set_event_status(eid: int, status: str, note: str = ""):
    async with Session() as s:
        e = await s.get(Event, eid)
        if e:
            e.status = status
            if note:
                e.note = note
            await s.commit()


async def events_between(elderly_id: int, start: datetime, end: datetime) -> list[Event]:
    async with Session() as s:
        r = await s.execute(select(Event).where(
            and_(Event.elderly_id == elderly_id,
                 Event.created_at >= start,
                 Event.created_at <= end)
        ).order_by(Event.created_at))
        return list(r.scalars().all())


async def all_events(elderly_id: int) -> list[Event]:
    async with Session() as s:
        r = await s.execute(select(Event).where(
            Event.elderly_id == elderly_id
        ).order_by(Event.created_at))
        return list(r.scalars().all())


# ============================================================
# MEASUREMENTS
# ============================================================

async def add_measurement(elderly_id: int, kind: str, value: str,
                          event_id=None, note: str = "") -> Measurement:
    async with Session() as s:
        m = Measurement(elderly_id=elderly_id, kind=kind, value=value,
                        event_id=event_id, note=note)
        s.add(m)
        await s.commit()
        await s.refresh(m)
        return m


async def list_measurements(elderly_id: int, limit: int = 50) -> list[Measurement]:
    async with Session() as s:
        r = await s.execute(select(Measurement).where(
            Measurement.elderly_id == elderly_id
        ).order_by(Measurement.created_at.desc()).limit(limit))
        return list(r.scalars().all())


async def all_measurements(elderly_id: int) -> list[Measurement]:
    async with Session() as s:
        r = await s.execute(select(Measurement).where(
            Measurement.elderly_id == elderly_id
        ).order_by(Measurement.created_at))
        return list(r.scalars().all())


async def measurements_between(elderly_id: int, start: datetime,
                                end: datetime) -> list[Measurement]:
    async with Session() as s:
        r = await s.execute(select(Measurement).where(
            and_(Measurement.elderly_id == elderly_id,
                 Measurement.created_at >= start,
                 Measurement.created_at <= end)
        ).order_by(Measurement.created_at))
        return list(r.scalars().all())


# ============================================================
# WELLBEING LOGS
# ============================================================

async def log_wellbeing(elderly_id: int, text_val: str, category: str,
                        source: str = "text"):
    async with Session() as s:
        entry = WellbeingLog(
            elderly_id=elderly_id,
            text=text_val[:1000],
            category=category[:20],
            source=source[:20],
        )
        s.add(entry)
        await s.commit()


async def list_wellbeing_logs(elderly_id: int, limit: int = 50) -> list[WellbeingLog]:
    async with Session() as s:
        r = await s.execute(select(WellbeingLog).where(
            WellbeingLog.elderly_id == elderly_id
        ).order_by(WellbeingLog.created_at.desc()).limit(limit))
        return list(r.scalars().all())


async def all_wellbeing_logs(elderly_id: int) -> list[WellbeingLog]:
    async with Session() as s:
        r = await s.execute(select(WellbeingLog).where(
            WellbeingLog.elderly_id == elderly_id
        ).order_by(WellbeingLog.created_at))
        return list(r.scalars().all())


# ============================================================
# HELP REQUESTS
# ============================================================

async def create_help_request(user_id: int, family_id, text_val: str) -> HelpRequest:
    async with Session() as s:
        hr = HelpRequest(user_id=user_id, family_id=family_id,
                         request_text=text_val)
        s.add(hr)
        await s.commit()
        await s.refresh(hr)
        return hr


async def get_help_request(rid: int) -> HelpRequest | None:
    async with Session() as s:
        return await s.get(HelpRequest, rid)


async def list_user_help_requests(user_id: int) -> list[HelpRequest]:
    async with Session() as s:
        r = await s.execute(select(HelpRequest).where(
            HelpRequest.user_id == user_id
        ).order_by(HelpRequest.created_at.desc()))
        return list(r.scalars().all())


async def list_all_help_requests() -> list[HelpRequest]:
    async with Session() as s:
        r = await s.execute(
            select(HelpRequest).order_by(HelpRequest.created_at.desc())
        )
        return list(r.scalars().all())


async def list_new_help_requests() -> list[HelpRequest]:
    async with Session() as s:
        r = await s.execute(select(HelpRequest).where(
            HelpRequest.status == "new"
        ).order_by(HelpRequest.created_at.desc()))
        return list(r.scalars().all())


async def reply_help_request(rid: int, reply_text: str):
    async with Session() as s:
        hr = await s.get(HelpRequest, rid)
        if hr:
            hr.reply_text = reply_text
            hr.status = "replied"
            hr.replied_at = datetime.now()
            await s.commit()


# ============================================================
# AUDIT LOG
# ============================================================

async def list_audit(family_id: int, limit: int = 100) -> list[AuditLog]:
    async with Session() as s:
        r = await s.execute(select(AuditLog).where(
            AuditLog.family_id == family_id
        ).order_by(AuditLog.created_at.desc()).limit(limit))
        return list(r.scalars().all())


# ============================================================
# ALERT ACK
# ============================================================

async def create_alert_ack(elderly_id: int, user_id: int, kind: str,
                           summary: str = ""):
    async with Session() as s:
        a = AlertAck(
            elderly_id=elderly_id, user_id=user_id,
            kind=kind[:30], summary=summary[:300],
        )
        s.add(a)
        await s.commit()


async def get_alert_ack(elderly_id: int, user_id: int, kind: str):
    async with Session() as s:
        r = await s.execute(select(AlertAck).where(
            and_(AlertAck.elderly_id == elderly_id,
                 AlertAck.user_id == user_id,
                 AlertAck.kind == kind)
        ).order_by(AlertAck.created_at.desc()).limit(1))
        return r.scalars().first()


async def who_acknowledged(elderly_id: int, kind: str):
    async with Session() as s:
        cutoff = datetime.now() - timedelta(hours=2)
        r = await s.execute(select(AlertAck).where(
            and_(AlertAck.elderly_id == elderly_id,
                 AlertAck.kind == kind,
                 AlertAck.created_at >= cutoff)
        ).order_by(AlertAck.created_at.desc()))
        return list(r.scalars().all())


# ============================================================
# USER MUTE
# ============================================================

async def mute_user(user_id: int, minutes: int):
    async with Session() as s:
        until = datetime.now() + timedelta(minutes=minutes)
        m = UserMute(user_id=user_id, until_at=until)
        s.add(m)
        await s.commit()
        return until


async def unmute_user(user_id: int):
    async with Session() as s:
        from sqlalchemy import delete as sqldel
        await s.execute(sqldel(UserMute).where(UserMute.user_id == user_id))
        await s.commit()


async def is_user_muted(user_id: int) -> bool:
    async with Session() as s:
        r = await s.execute(select(UserMute).where(
            and_(UserMute.user_id == user_id,
                 UserMute.until_at > datetime.now())
        ).order_by(UserMute.until_at.desc()).limit(1))
        return r.scalars().first() is not None


async def get_mute_until(user_id: int):
    async with Session() as s:
        r = await s.execute(select(UserMute).where(
            and_(UserMute.user_id == user_id,
                 UserMute.until_at > datetime.now())
        ).order_by(UserMute.until_at.desc()).limit(1))
        m = r.scalars().first()
        return m.until_at if m else None


# ============================================================
# NOTES
# ============================================================

async def add_note(elderly_id: int, text: str, remind_at: datetime,
                   created_by: int | None = None) -> Note:
    async with Session() as s:
        n = Note(elderly_id=elderly_id, text=text[:200],
                 remind_at=remind_at, created_by=created_by)
        s.add(n)
        await s.commit()
        await s.refresh(n)
        return n


async def get_note(nid: int) -> Note | None:
    async with Session() as s:
        return await s.get(Note, nid)


async def list_notes_for_elderly(elderly_id: int, only_pending: bool = True):
    async with Session() as s:
        q = select(Note).where(Note.elderly_id == elderly_id)
        if only_pending:
            q = q.where(Note.status == "pending")
        q = q.order_by(Note.remind_at)
        r = await s.execute(q)
        return list(r.scalars().all())


async def list_future_notes() -> list[Note]:
    async with Session() as s:
        r = await s.execute(select(Note).where(
            and_(Note.status == "pending",
                 Note.remind_at > datetime.now())
        ).order_by(Note.remind_at))
        return list(r.scalars().all())


async def mark_note_sent(nid: int):
    async with Session() as s:
        n = await s.get(Note, nid)
        if n:
            n.status = "sent"
            await s.commit()


async def mark_note_done(nid: int, feedback: str = ""):
    async with Session() as s:
        n = await s.get(Note, nid)
        if n:
            n.status = "done"
            if feedback:
                n.feedback = feedback[:20]
            await s.commit()


async def delete_note(nid: int):
    async with Session() as s:
        n = await s.get(Note, nid)
        if n:
            await s.delete(n)
            await s.commit()


# ============================================================
# ADMIN STATS
# ============================================================

async def admin_stats() -> dict:
    async with Session() as s:
        fam = (await s.execute(select(Family))).scalars().all()
        eld = (await s.execute(select(Elderly))).scalars().all()
        usr = (await s.execute(select(User))).scalars().all()
        today = date.today().isoformat()
        today_start = datetime.combine(date.today(), datetime.min.time())
        today_events = (await s.execute(select(Event).where(
            Event.created_at >= today_start
        ))).scalars().all()
        help_all = (await s.execute(select(HelpRequest))).scalars().all()
        help_new = [h for h in help_all if h.status == "new"]
        help_today = [h for h in help_all if h.created_at >= today_start]
        return {
            "families": len(fam),
            "elderly": len(eld),
            "users": len(usr),
            "linked_elderly": sum(1 for e in eld if e.user_id),
            "awake_today": sum(1 for e in eld if e.wake_date == today),
            "events_today": len(today_events),
            "alarms_today": sum(1 for e in today_events if e.status == "alarm"),
            "help_today": len(help_today),
            "help_total": len(help_all),
            "help_new": len(help_new),
        }
        
        
        # ============================================================
# ANALYTICS
# ============================================================

async def weekly_progress(elderly_id: int, days: int = 7):
    """Возвращает список дней с разбивкой выполненных/пропущенных задач."""
    end = datetime.now()
    start = end - timedelta(days=days)
    async with Session() as s:
        r = await s.execute(select(Event).where(
            and_(Event.elderly_id == elderly_id,
                 Event.kind == "routine",
                 Event.created_at >= start,
                 Event.created_at <= end)
        ).order_by(Event.created_at))
        events = list(r.scalars().all())

    by_day = {}
    for e in events:
        key = e.created_at.strftime("%Y-%m-%d")
        if key not in by_day:
            by_day[key] = {"done": 0, "skipped": 0, "alarm": 0,
                           "pending": 0, "total": 0}
        by_day[key]["total"] = by_day[key]["total"] + 1
        if e.status in by_day[key]:
            by_day[key][e.status] = by_day[key][e.status] + 1

    result = []
    for i in range(days):
        d = (end - timedelta(days=days - 1 - i)).date()
        key = d.isoformat()
        stats = by_day.get(key, {"done": 0, "skipped": 0, "alarm": 0,
                                 "pending": 0, "total": 0})
        stats["date"] = d
        result.append(stats)
    return result


async def family_activity_log(family_id: int, elderly_ids: list,
                              hours: int = 24, limit: int = 50):
    """Лента событий за период. Возвращает список кортежей (time, text)."""
    since = datetime.now() - timedelta(hours=hours)
    log_items = []

    if not elderly_ids:
        return []

    async with Session() as s:
        r = await s.execute(select(Event).where(
            and_(Event.elderly_id.in_(elderly_ids),
                 Event.created_at >= since)
        ).order_by(Event.created_at))
        for ev in r.scalars().all():
            t = ev.created_at.strftime("%H:%M")
            if ev.kind == "routine":
                if ev.status == "done":
                    text = "✅ задача выполнена"
                elif ev.status == "skipped":
                    text = "⏭ задача пропущена"
                elif ev.status == "alarm":
                    text = "⚠️ задача не подтверждена"
                else:
                    text = "⏳ задача ожидает"
                log_items.append((ev.created_at, t, text, ev.elderly_id))
            elif ev.kind == "wellbeing":
                if ev.status in ("bad", "help", "critical"):
                    log_items.append((ev.created_at, t,
                                      "⚠️ самочувствие: " + ev.status,
                                      ev.elderly_id))

        r2 = await s.execute(select(WellbeingLog).where(
            and_(WellbeingLog.elderly_id.in_(elderly_ids),
                 WellbeingLog.created_at >= since)
        ).order_by(WellbeingLog.created_at))
        for lg in r2.scalars().all():
            if lg.category in ("bad", "help", "critical"):
                t = lg.created_at.strftime("%H:%M")
                log_items.append((lg.created_at, t,
                                  "💬 жалоба: " + lg.text[:40],
                                  lg.elderly_id))

        r3 = await s.execute(select(AlertAck).where(
            and_(AlertAck.elderly_id.in_(elderly_ids),
                 AlertAck.created_at >= since)
        ).order_by(AlertAck.created_at))
        for a in r3.scalars().all():
            t = a.created_at.strftime("%H:%M")
            log_items.append((a.created_at, t,
                              "✅ взято на контроль", a.elderly_id))

    log_items.sort(key=lambda x: x[0], reverse=True)
    return log_items[:limit]


async def get_elderly_names(elderly_ids: list) -> dict:
    """Возвращает {id: name} для списка близких."""
    if not elderly_ids:
        return {}
    async with Session() as s:
        r = await s.execute(select(Elderly).where(Elderly.id.in_(elderly_ids)))
        return {e.id: e.name for e in r.scalars().all()}
        
        
        # ============================================================
# LEAVE FAMILY
# ============================================================

async def leave_family(user_id: int) -> dict:
    """
    Выход пользователя из семьи.
    Возвращает:
      {
        "ok": bool,
        "reason": str,           # если не получилось
        "role": str,             # роль, с которой вышел
        "family_id": int,
        "family_name": str,
        "new_owner_id": int|None,  # если был owner и передал
        "family_deleted": bool,    # если был последним
      }
    """
    from sqlalchemy import delete as sqldel
    async with Session() as s:
        r = await s.execute(select(FamilyMember).where(
            FamilyMember.user_id == user_id
        ).order_by(FamilyMember.id.asc()))
        m = r.scalars().first()
        if not m:
            return {"ok": False, "reason": "Вы не состоите в семье."}

        f = await s.get(Family, m.family_id)
        if not f:
            await s.delete(m)
            await s.commit()
            return {"ok": False, "reason": "Семья не найдена."}

        result = {
            "ok": True,
            "role": m.role,
            "family_id": f.id,
            "family_name": f.name,
            "new_owner_id": None,
            "family_deleted": False,
        }

        if m.role == "owner":
            # Ищем других участников
            r2 = await s.execute(select(FamilyMember).where(
                and_(FamilyMember.family_id == f.id,
                     FamilyMember.user_id != user_id)
            ).order_by(FamilyMember.id.asc()))
            others = list(r2.scalars().all())
            if not others:
                # Владелец один — удаляем всю семью
                r3 = await s.execute(
                    select(Elderly).where(Elderly.family_id == f.id)
                )
                for e in r3.scalars().all():
                    await s.execute(sqldel(Routine).where(Routine.elderly_id == e.id))
                    await s.execute(sqldel(Event).where(Event.elderly_id == e.id))
                    await s.execute(sqldel(WellbeingLog).where(WellbeingLog.elderly_id == e.id))
                    await s.execute(sqldel(Measurement).where(Measurement.elderly_id == e.id))
                    await s.execute(sqldel(Note).where(Note.elderly_id == e.id))
                    await s.execute(sqldel(AlertAck).where(AlertAck.elderly_id == e.id))
                    await s.delete(e)
                await s.execute(sqldel(CustomTemplate).where(CustomTemplate.family_id == f.id))
                await s.delete(m)
                await s.delete(f)
                await s.commit()
                result["family_deleted"] = True
                return result

            # Передаём владение первому оставшемуся
            new_owner = others[0]
            # приоритет — модератор, если он есть
            for o in others:
                if o.role == "moderator":
                    new_owner = o
                    break
            new_owner.role = "owner"
            f.owner_user_id = new_owner.user_id
            result["new_owner_id"] = new_owner.user_id
            await s.delete(m)
            await s.commit()
            return result

        # Обычный участник или модератор — просто выходим
        await s.delete(m)
        await s.commit()
        return result