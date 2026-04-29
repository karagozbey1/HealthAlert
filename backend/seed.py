from __future__ import annotations

import logging
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import select

from auth import hash_password
from database import AsyncSessionLocal
from models import (
    AlertEvent,
    AnomalyEvent,
    AppSettings,
    HistoryItem,
    LinkCode,
    NotificationItem,
    SimulationState,
    User,
    UserRelation,
)

logger = logging.getLogger("seed")

DEMO_USERS = [
    dict(
        email="self@demo.com",
        password="demo1234",
        role="SELF",
        full_name="Ali Yilmaz",
        phone="+90 555 100 0001",
        birth_date="1965-03-15",
    ),
    dict(
        email="relative@demo.com",
        password="demo1234",
        role="RELATIVE",
        full_name="Ahmet Yilmaz",
        phone="+90 555 100 0002",
        birth_date="1990-07-20",
    ),
    dict(
        email="doctor@demo.com",
        password="demo1234",
        role="DOCTOR",
        full_name="Dr. Elif Kaya",
        phone="+90 555 100 0003",
        birth_date="1980-11-05",
    ),
]

# Demo kullanıcıları ve ilişkilerini oluşturur.
async def seed_demo_data() -> None:
    async with AsyncSessionLocal() as db:
        created_users: dict[str, User] = {}

        for u_data in DEMO_USERS:
            result = await db.execute(select(User).where(User.email == u_data["email"]))
            existing = result.scalar_one_or_none()
            if existing:
                created_users[u_data["role"]] = existing
                continue

            user = User(
                id=str(uuid4()),
                email=u_data["email"],
                password_hash=hash_password(u_data["password"]),
                role=u_data["role"],
                full_name=u_data["full_name"],
                phone=u_data["phone"],
                birth_date=u_data["birth_date"],
            )
            db.add(user)
            db.add(AppSettings(user_id=user.id))
            if u_data["role"] == "SELF":
                db.add(SimulationState(user_id=user.id))
            created_users[u_data["role"]] = user
            logger.info("Created demo user: %s (%s)", u_data["email"], u_data["role"])

        await db.flush()

        self_user = created_users.get("SELF")
        relative_user = created_users.get("RELATIVE")
        doctor_user = created_users.get("DOCTOR")

        if self_user and relative_user and doctor_user:
            rel_check = await db.execute(
                select(UserRelation).where(
                    UserRelation.self_user_id == self_user.id,
                    UserRelation.is_active == True,
                )
            )
            existing_rels = rel_check.scalars().all()

            if not existing_rels:
                db.add(UserRelation(
                    id=str(uuid4()),
                    self_user_id=self_user.id,
                    linked_user_id=relative_user.id,
                    relation_type="RELATIVE",
                    is_active=True,
                ))
                db.add(UserRelation(
                    id=str(uuid4()),
                    self_user_id=self_user.id,
                    linked_user_id=doctor_user.id,
                    relation_type="DOCTOR",
                    is_active=True,
                ))

                now = datetime.utcnow()
                history_items = [
                    HistoryItem(
                        id=str(uuid4()),
                        user_id=self_user.id,
                        item_type="alert",
                        title="Kritik SpO2 Alarmı",
                        subtitle="Oksijen doygunluğu %88'e düştü. Acil kişiler bilgilendirildi.",
                        timestamp=now - timedelta(days=3),
                        severity="critical",
                        outcome="acknowledged",
                    ),
                    HistoryItem(
                        id=str(uuid4()),
                        user_id=self_user.id,
                        item_type="anomaly",
                        title="Nabız Anomalisi",
                        subtitle="Sabah izlemesinde nabız 124 bpm'e ulaştı.",
                        timestamp=now - timedelta(days=2),
                        severity="warning",
                    ),
                    HistoryItem(
                        id=str(uuid4()),
                        user_id=self_user.id,
                        item_type="status",
                        title="İzleme Sürdürüldü",
                        subtitle="Dinlendikten sonra vital değerler normale döndü.",
                        timestamp=now - timedelta(days=2, hours=1),
                        severity="normal",
                    ),
                    HistoryItem(
                        id=str(uuid4()),
                        user_id=self_user.id,
                        item_type="anomaly",
                        title="SpO2 İzleme Olayı",
                        subtitle="Hafif egzersiz sırasında SpO2 %95. Kendiliğinden normale döndü.",
                        timestamp=now - timedelta(hours=6),
                        severity="watch",
                    ),
                ]
                for h in history_items:
                    db.add(h)

                anomalies = [
                    AnomalyEvent(
                        id=str(uuid4()),
                        user_id=self_user.id,
                        metric="SpO2",
                        value=88.0,
                        unit="%",
                        severity="critical",
                        detected_at=now - timedelta(days=3),
                        summary="Oksijen doygunluğu kritik seviyede düşük.",
                    ),
                    AnomalyEvent(
                        id=str(uuid4()),
                        user_id=self_user.id,
                        metric="Nabız",
                        value=124.0,
                        unit="bpm",
                        severity="warning",
                        detected_at=now - timedelta(days=2),
                        summary="Nabız uyarı eşiğinin üzerinde.",
                    ),
                    AnomalyEvent(
                        id=str(uuid4()),
                        user_id=self_user.id,
                        metric="SpO2",
                        value=95.0,
                        unit="%",
                        severity="watch",
                        detected_at=now - timedelta(hours=6),
                        summary="Egzersiz sırasında SpO2 hafifçe düşük.",
                    ),
                ]
                for a in anomalies:
                    db.add(a)

                notifs = [
                    NotificationItem(
                        id=str(uuid4()),
                        recipient_id=relative_user.id,
                        sender_id=self_user.id,
                        title="Ali Yılmaz ile bağlantı kuruldu",
                        body="Artık Ali Yılmaz'ı yakın olarak izliyorsunuz.",
                        notification_type="link",
                        is_read=False,
                        created_at=now - timedelta(days=3),
                    ),
                    NotificationItem(
                        id=str(uuid4()),
                        recipient_id=doctor_user.id,
                        sender_id=self_user.id,
                        title="Yeni Hasta: Ali Yılmaz",
                        body="Ali Yılmaz sizi doktoru olarak ekledi.",
                        notification_type="link",
                        is_read=False,
                        created_at=now - timedelta(days=3),
                    ),
                    NotificationItem(
                        id=str(uuid4()),
                        recipient_id=relative_user.id,
                        sender_id=self_user.id,
                        title="🚨 Kritik Alarm – Ali Yılmaz",
                        body="Ali Yılmaz: SpO2 kritik seviyede düşük (%88). Acil kişiler bilgilendirildi.",
                        notification_type="alert",
                        is_read=True,
                        created_at=now - timedelta(days=3, minutes=5),
                    ),
                    NotificationItem(
                        id=str(uuid4()),
                        recipient_id=doctor_user.id,
                        sender_id=self_user.id,
                        title="🚨 Kritik Alarm – Ali Yılmaz",
                        body="Ali Yılmaz: SpO2 kritik seviyede düşük (%88). Lütfen inceleyin.",
                        notification_type="alert",
                        is_read=False,
                        created_at=now - timedelta(days=3, minutes=5),
                    ),
                ]
                for n in notifs:
                    db.add(n)

                db.add(LinkCode(
                    id=str(uuid4()),
                    code="831047",
                    owner_id=relative_user.id,
                    code_type="RELATIVE",
                    is_active=True,
                    uses_remaining=5,
                    expires_at=datetime.utcnow() + timedelta(days=365),
                ))
                db.add(LinkCode(
                    id=str(uuid4()),
                    code="204815",
                    owner_id=doctor_user.id,
                    code_type="DOCTOR",
                    is_active=True,
                    uses_remaining=5,
                    expires_at=datetime.utcnow() + timedelta(days=365),
                ))

                logger.info("Demo seed data created successfully.")

        await db.commit()
