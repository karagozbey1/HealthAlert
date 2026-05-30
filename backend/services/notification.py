from __future__ import annotations

import logging
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import NotificationItem, UserRelation
from services.push_service import push_to_user

logger = logging.getLogger("healthalert.notification")

# Hastanın bağlı tüm kullanıcılarına bildirim gönderir.
async def notify_linked_users(
    db: AsyncSession,
    self_user_id: str,
    self_user_name: str,
    title: str,
    body: str,
    notification_type: str,
    reference_id: str | None = None,
    reference_type: str | None = None,
    *,
    repos=None,
) -> None:
    """notification servisindeki HealthAlert iş kuralını uygular."""
    if repos is not None:
        relations = await repos.relations.find_active_by_self_user(self_user_id)
        for rel in relations:
            full_body = f"{self_user_name}: {body}"
            await repos.notifications.create({
                "id": str(uuid4()),
                "recipient_id": rel["linked_user_id"],
                "sender_id": self_user_id,
                "title": title,
                "body": full_body,
                "notification_type": notification_type,
                "reference_id": reference_id,
                "reference_type": reference_type,
                "is_read": False,
            })
            try:
                await push_to_user(
                    db, rel["linked_user_id"], title, full_body,
                    data={"type": notification_type, "reference_id": reference_id or ""},
                )
            except Exception as exc:
                logger.debug("Push delivery skipped: %s", exc)
        return

    result = await db.execute(
        select(UserRelation).where(
            UserRelation.self_user_id == self_user_id,
            UserRelation.is_active == True,
        )
    )
    relations = result.scalars().all()

    for rel in relations:
        full_body = f"{self_user_name}: {body}"
        notif = NotificationItem(
            id=str(uuid4()),
            recipient_id=rel.linked_user_id,
            sender_id=self_user_id,
            title=title,
            body=full_body,
            notification_type=notification_type,
            reference_id=reference_id,
            reference_type=reference_type,
            is_read=False,
        )
        db.add(notif)
        try:
            await push_to_user(
                db, rel.linked_user_id, title, full_body,
                data={"type": notification_type, "reference_id": reference_id or ""},
            )
        except Exception as exc:
            logger.debug("Push delivery skipped: %s", exc)

# Tek bir alıcıya bildirim gönderir.
async def notify_single(
    db: AsyncSession,
    recipient_id: str,
    title: str,
    body: str,
    notification_type: str,
    reference_id: str | None = None,
    reference_type: str | None = None,
    sender_id: str | None = None,
    *,
    repos=None,
) -> None:
    """notification servisindeki HealthAlert iş kuralını uygular."""
    if repos is not None:
        await repos.notifications.create({
            "id": str(uuid4()),
            "recipient_id": recipient_id,
            "sender_id": sender_id,
            "title": title,
            "body": body,
            "notification_type": notification_type,
            "reference_id": reference_id,
            "reference_type": reference_type,
            "is_read": False,
        })
        try:
            await push_to_user(
                db, recipient_id, title, body,
                data={"type": notification_type, "reference_id": reference_id or ""},
            )
        except Exception as exc:
            logger.debug("Push delivery skipped: %s", exc)
        return

    notif = NotificationItem(
        id=str(uuid4()),
        recipient_id=recipient_id,
        title=title,
        body=body,
        notification_type=notification_type,
        reference_id=reference_id,
        reference_type=reference_type,
        sender_id=sender_id,
        is_read=False,
    )
    db.add(notif)
    try:
        await push_to_user(
            db, recipient_id, title, body,
            data={"type": notification_type, "reference_id": reference_id or ""},
        )
    except Exception as exc:
        logger.debug("Push delivery skipped: %s", exc)
