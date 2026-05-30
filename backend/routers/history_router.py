from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import User
from repositories.factory import RepoSet
from routers.deps import get_current_user, get_repo_set
from schemas import HistoryResponse

router = APIRouter(prefix="/history", tags=["history"])

# Mevcut SELF kullanicisina ait tarihce kayitlarini dondurur.
@router.get("", response_model=list[HistoryResponse])
async def get_my_history(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    """Yetkili kullanıcı için geçmiş okuma isteğini işler."""
    if current_user.role != "SELF":
        raise HTTPException(status_code=403, detail="SELF role required")
    return await repos.history.list_by_user(current_user.id)

# Yetkili baglantilar icin kullanici tarihcesini dondurur.
@router.get("/{user_id}", response_model=list[HistoryResponse])
async def get_user_history(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    """Yetkili kullanıcı için geçmiş okuma isteğini işler."""
    if current_user.id != user_id:
        link = await repos.relations.find_active_link(user_id, current_user.id)
        if link is None:
            raise HTTPException(status_code=403, detail="Access denied")
    return await repos.history.list_by_user(user_id)
