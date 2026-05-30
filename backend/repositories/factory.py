from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from config import settings

logger = logging.getLogger("repositories.factory")

@dataclass
class RepoSet:
    users: Any
    link_codes: Any
    relations: Any
    live_status: Any
    anomalies: Any
    alerts: Any
    post_events: Any
    history: Any
    notifications: Any
    clinical_notes: Any
    app_settings: Any
    simulation: Any
    devices: Any
    baselines: Any
    learning: Any
    personalization: Any
    assistant: Any

# SQLite repository setini oluşturur.
def _build_sqlite(db) -> RepoSet:
    from repositories.sqlite import (
        SqliteAlertRepo,
        SqliteAnomalyRepo,
        SqliteAssistantRepo,
        SqliteBaselineRepo,
        SqliteClinicalNoteRepo,
        SqliteDeviceRepo,
        SqliteHistoryRepo,
        SqliteLearningRepo,
        SqliteLinkCodeRepo,
        SqliteLiveStatusRepo,
        SqliteNotificationRepo,
        SqlitePersonalizationRepo,
        SqlitePostEventRepo,
        SqliteRelationRepo,
        SqliteSettingsRepo,
        SqliteSimulationStateRepo,
        SqliteUserRepo,
    )
    return RepoSet(
        users=SqliteUserRepo(db),
        link_codes=SqliteLinkCodeRepo(db),
        relations=SqliteRelationRepo(db),
        live_status=SqliteLiveStatusRepo(db),
        anomalies=SqliteAnomalyRepo(db),
        alerts=SqliteAlertRepo(db),
        post_events=SqlitePostEventRepo(db),
        history=SqliteHistoryRepo(db),
        notifications=SqliteNotificationRepo(db),
        clinical_notes=SqliteClinicalNoteRepo(db),
        app_settings=SqliteSettingsRepo(db),
        simulation=SqliteSimulationStateRepo(db),
        devices=SqliteDeviceRepo(db),
        baselines=SqliteBaselineRepo(db),
        learning=SqliteLearningRepo(db),
        personalization=SqlitePersonalizationRepo(db),
        assistant=SqliteAssistantRepo(db),
    )

# Firebase repository setini oluşturur.
def _build_firebase() -> RepoSet:
    from firebase_client import get_firestore_client
    from repositories.firebase import (
        FirebaseAlertRepo,
        FirebaseAnomalyRepo,
        FirebaseBaselineRepo,
        FirebaseClinicalNoteRepo,
        FirebaseDeviceRepo,
        FirebaseHistoryRepo,
        FirebaseLinkCodeRepo,
        FirebaseLiveStatusRepo,
        FirebaseNotificationRepo,
        FirebasePostEventRepo,
        FirebaseRelationRepo,
        FirebaseSettingsRepo,
        FirebaseSimulationStateRepo,
        FirebaseUserRepo,
    )
    fs = get_firestore_client()
    return RepoSet(
        users=FirebaseUserRepo(fs),
        link_codes=FirebaseLinkCodeRepo(fs),
        relations=FirebaseRelationRepo(fs),
        live_status=FirebaseLiveStatusRepo(fs),
        anomalies=FirebaseAnomalyRepo(fs),
        alerts=FirebaseAlertRepo(fs),
        post_events=FirebasePostEventRepo(fs),
        history=FirebaseHistoryRepo(fs),
        notifications=FirebaseNotificationRepo(fs),
        clinical_notes=FirebaseClinicalNoteRepo(fs),
        app_settings=FirebaseSettingsRepo(fs),
        simulation=FirebaseSimulationStateRepo(fs),
        devices=FirebaseDeviceRepo(fs),
        baselines=FirebaseBaselineRepo(fs),
        # Ogrenme dongusu Firebase modunda henuz yalnizca SQLite tarafinda calisir.
        learning=None,
        personalization=None,
        assistant=None,
    )

class _HybridRepo:

    # Birincil ve ikincil repository örneklerini saklar.
    def __init__(self, primary, secondary):
        self._primary = primary
        self._secondary = secondary

    # Okuma metodlarını primary'e, yazma metodlarını her ikisine yönlendirir.
    def __getattr__(self, name):
        primary_fn = getattr(self._primary, name)
        secondary_fn = getattr(self._secondary, name, None)

        if name.startswith(("get", "list", "find", "mark")):
            return primary_fn

        if secondary_fn is None:
            return primary_fn

        # Yazma işlemlerini önce yerel depoya, sonra ikincil depoya yollar.
        async def _hybrid_write(*args, **kwargs):
            result = await primary_fn(*args, **kwargs)
            try:
                await secondary_fn(*args, **kwargs)
            except Exception as exc:
                import logging
                logging.getLogger("hybrid_repo").warning(
                    "Firebase write failed for %s.%s – data saved locally. Error: %s",
                    type(self._primary).__name__, name, exc,
                )
            return result

        return _hybrid_write

# Hibrit (SQLite + Firebase) repository setini oluşturur.
def _build_hybrid(db) -> RepoSet:
    sq = _build_sqlite(db)
    from firebase_client import get_firestore_client

    if get_firestore_client() is None:
        logger.warning("Hybrid Firebase repository disabled; using SQLite repositories only.")
        return sq

    try:
        fb = _build_firebase()
    except ModuleNotFoundError as exc:
        logger.warning(
            "Hybrid Firebase repository dependency missing; using SQLite repositories only. Error: %s",
            exc,
        )
        return sq

    return RepoSet(
        users=_HybridRepo(sq.users, fb.users),
        link_codes=_HybridRepo(sq.link_codes, fb.link_codes),
        relations=_HybridRepo(sq.relations, fb.relations),
        live_status=_HybridRepo(sq.live_status, fb.live_status),
        anomalies=_HybridRepo(sq.anomalies, fb.anomalies),
        alerts=_HybridRepo(sq.alerts, fb.alerts),
        post_events=_HybridRepo(sq.post_events, fb.post_events),
        history=_HybridRepo(sq.history, fb.history),
        notifications=_HybridRepo(sq.notifications, fb.notifications),
        clinical_notes=_HybridRepo(sq.clinical_notes, fb.clinical_notes),
        app_settings=_HybridRepo(sq.app_settings, fb.app_settings),
        simulation=_HybridRepo(sq.simulation, fb.simulation),
        devices=_HybridRepo(sq.devices, fb.devices),
        baselines=sq.baselines,
        # Ogrenme dongusu hibrit modda SQLite birincil olarak kullanilir.
        learning=sq.learning,
        personalization=sq.personalization,
        assistant=sq.assistant,
    )

# DATA_MODE'a göre RepoSet döndürür.
def get_repos(db=None, mode: str | None = None) -> RepoSet:
    m = (mode or settings.DATA_MODE).lower()
    if m == "firebase":
        return _build_firebase()
    if m == "hybrid":
        if db is None:
            raise ValueError("hybrid mode requires an AsyncSession (db)")
        return _build_hybrid(db)
    if db is None:
        raise ValueError("sqlite mode requires an AsyncSession (db)")
    return _build_sqlite(db)
