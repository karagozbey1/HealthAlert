from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import User
from repositories.factory import RepoSet
from routers.deps import get_current_user, get_repo_set
from schemas import LiveStatusResponse

router = APIRouter(prefix="/live", tags=["live-status"])

@router.get("/{user_id}", response_model=LiveStatusResponse)
async def get_live_status(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    if current_user.id != user_id:
        link = await repos.relations.find_active_link(user_id, current_user.id)
        if link is None:
            raise HTTPException(status_code=403, detail="Access denied")

    live = await repos.live_status.get_by_user(user_id)
    if live is None:
        raise HTTPException(status_code=404, detail="No live data yet")
    return live
