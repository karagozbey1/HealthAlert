from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models import DeviceToken

logger = logging.getLogger("healthalert.push")

_FCM_URL = "https://fcm.googleapis.com/fcm/send"

_MAX_RETRIES = 2
_RETRY_TIMEOUT = 5.0

_push_stats: Dict[str, Any] = {
    "total_attempts": 0,
    "total_successes": 0,
    "total_failures": 0,
    "invalid_tokens_cleaned": 0,
    "last_attempt_at": None,
    "last_success_at": None,
    "last_error": None,
}

# Push altyapisinin mevcut durumunu ve temel sayaçlarini ozetler.
def get_push_status() -> Dict[str, Any]:
    """push servisinde gereken veriyi okuyup çağırana döndürür."""
    fcm_key_set = bool(settings.FCM_SERVER_KEY)
    push_mode = settings.NOTIFICATION_MODE == "push"
    return {
        "notification_mode": settings.NOTIFICATION_MODE,
        "push_enabled": push_mode,
        "fcm_key_configured": fcm_key_set,
        "push_ready": push_mode and fcm_key_set,
        "push_effective_mode": (
            "live_push" if (push_mode and fcm_key_set) else
            "push_degraded_to_poll" if (push_mode and not fcm_key_set) else
            "poll_only"
        ),
        "stats": dict(_push_stats),
    }

# Tek bir cihaza FCM istegi gonderip sonucu fail-open bicimde dondurur.
async def _send_fcm_message(
    token: str,
    title: str,
    body: str,
    data: Optional[dict] = None,
) -> Dict[str, Any]:
    """push servisindeki HealthAlert iş kuralını uygular."""
    if not settings.FCM_SERVER_KEY:
        return {"ok": False, "token_invalid": False, "detail": "No FCM_SERVER_KEY configured."}

    payload = {
        "to": token,
        "notification": {"title": title, "body": body},
        "data": data or {},
        "android": {
            "priority": "high",
        },
    }
    headers = {
        "Authorization": f"key={settings.FCM_SERVER_KEY}",
        "Content-Type": "application/json",
    }

    last_error = ""
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            timeout = _RETRY_TIMEOUT * attempt
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(_FCM_URL, json=payload, headers=headers)

                if resp.status_code == 200:
                    result = resp.json()
                    if result.get("success", 0) >= 1:
                        return {"ok": True, "token_invalid": False, "detail": "Delivered."}

                    results_list = result.get("results", [])
                    if results_list:
                        error_code = results_list[0].get("error", "")
                        if error_code in ("NotRegistered", "InvalidRegistration"):
                            return {
                                "ok": False,
                                "token_invalid": True,
                                "detail": f"Token invalid: {error_code}",
                            }

                    last_error = f"FCM delivery failure: {result}"
                    logger.warning("FCM attempt %d/%d failed: %s", attempt, _MAX_RETRIES, result)

                elif resp.status_code == 401:
                    return {
                        "ok": False,
                        "token_invalid": False,
                        "detail": "FCM authentication failed — check FCM_SERVER_KEY.",
                    }

                else:
                    last_error = f"FCM HTTP {resp.status_code}: {resp.text[:200]}"
                    logger.warning(
                        "FCM attempt %d/%d — HTTP %d: %s",
                        attempt, _MAX_RETRIES, resp.status_code, resp.text[:200],
                    )

        except httpx.TimeoutException:
            last_error = f"FCM timeout on attempt {attempt}/{_MAX_RETRIES}"
            logger.warning(last_error)

        except Exception as exc:
            last_error = f"FCM send error: {exc}"
            logger.error("FCM attempt %d/%d error: %s", attempt, _MAX_RETRIES, exc)

    return {"ok": False, "token_invalid": False, "detail": last_error}

# Gecersiz hale gelen token kaydini veritabanindan temizler.
async def _cleanup_invalid_token(db: AsyncSession, token: str, user_id: str) -> None:
    """push servisindeki HealthAlert iş kuralını uygular."""
    try:
        await db.execute(
            delete(DeviceToken).where(
                DeviceToken.user_id == user_id,
                DeviceToken.token == token,
            )
        )
        _push_stats["invalid_tokens_cleaned"] += 1
        logger.info(
            "Cleaned invalid FCM token %s…%s for user %s.",
            token[:8], token[-4:] if len(token) > 8 else "???", user_id,
        )
    except Exception as exc:
        logger.warning("Failed to clean invalid token: %s", exc)

# Kullaniciya ait tum cihaz tokenlarina push bildirimini yollar.
async def push_to_user(
    db: AsyncSession,
    user_id: str,
    title: str,
    body: str,
    data: Optional[dict] = None,
) -> int:
    """push servisindeki HealthAlert iş kuralını uygular."""
    if settings.NOTIFICATION_MODE != "push":
        return 0

    if not settings.FCM_SERVER_KEY:
        logger.debug("Push skipped for user %s — no FCM_SERVER_KEY.", user_id)
        return 0

    result = await db.execute(
        select(DeviceToken).where(DeviceToken.user_id == user_id)
    )
    tokens: List[DeviceToken] = list(result.scalars().all())

    if not tokens:
        logger.debug("No device tokens for user %s — push skipped.", user_id)
        return 0

    _push_stats["last_attempt_at"] = datetime.utcnow().isoformat()

    sent = 0
    for dt in tokens:
        _push_stats["total_attempts"] += 1
        delivery = await _send_fcm_message(dt.token, title, body, data)

        if delivery["ok"]:
            sent += 1
            _push_stats["total_successes"] += 1
            _push_stats["last_success_at"] = datetime.utcnow().isoformat()
        else:
            _push_stats["total_failures"] += 1
            _push_stats["last_error"] = delivery["detail"]

            if delivery["token_invalid"]:
                await _cleanup_invalid_token(db, dt.token, user_id)

            logger.info(
                "Push failed for token %s…%s (user %s): %s",
                dt.token[:8], dt.token[-4:] if len(dt.token) > 8 else "???",
                user_id, delivery["detail"],
            )

    logger.info("Push delivery for user %s: %d/%d tokens.", user_id, sent, len(tokens))
    return sent

# FCM anahtari ve erisilebilirligi icin temel smoke kontrolunu calistirir.
async def push_smoke_test(db: AsyncSession) -> Dict[str, Any]:
    """push servisindeki HealthAlert iş kuralını uygular."""
    checks = {
        "notification_mode_is_push": settings.NOTIFICATION_MODE == "push",
        "fcm_key_configured": bool(settings.FCM_SERVER_KEY),
        "fcm_endpoint_reachable": False,
    }

    if not checks["notification_mode_is_push"]:
        return {
            "ok": False,
            "checks": checks,
            "detail": "NOTIFICATION_MODE is not 'push'. Set NOTIFICATION_MODE=push to enable.",
        }

    if not checks["fcm_key_configured"]:
        return {
            "ok": False,
            "checks": checks,
            "detail": "FCM_SERVER_KEY is empty. Configure it to enable push delivery.",
        }

    try:
        headers = {
            "Authorization": f"key={settings.FCM_SERVER_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "to": "dry-run-test-token",
            "dry_run": True,
            "notification": {"title": "test", "body": "test"},
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(_FCM_URL, json=payload, headers=headers)

            if resp.status_code == 200:
                checks["fcm_endpoint_reachable"] = True
                result = resp.json()
                return {
                    "ok": True,
                    "checks": checks,
                    "detail": (
                        "FCM endpoint reachable and key accepted. "
                        "Push infrastructure is ready for real device tokens."
                    ),
                }
            elif resp.status_code == 401:
                return {
                    "ok": False,
                    "checks": checks,
                    "detail": "FCM key rejected (HTTP 401). Check FCM_SERVER_KEY value.",
                }
            else:
                return {
                    "ok": False,
                    "checks": checks,
                    "detail": f"FCM endpoint returned HTTP {resp.status_code}.",
                }

    except Exception as exc:
        return {
            "ok": False,
            "checks": checks,
            "detail": f"FCM endpoint unreachable: {exc}",
        }
