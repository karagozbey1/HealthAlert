from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import User
from repositories.factory import RepoSet
from routers.deps import get_current_user, get_repo_set
from schemas import UpdateProfileRequest, UserResponse

router = APIRouter(prefix="/users", tags=["users"])

# Giris yapan kullanicinin profilini dondurur.
@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Yetkili kullanıcı için kullanıcı okuma isteğini işler."""
    return current_user

# Giris yapan kullanicinin duzenlenebilir profil alanlarini gunceller.
@router.put("/me", response_model=UserResponse)
async def update_me(
    body: UpdateProfileRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    """Kullanıcı güncelleme isteğini doğrulayıp uygular."""
    updates = {}
    if body.full_name is not None:
        updates["full_name"] = body.full_name.strip()
    if body.phone is not None:
        updates["phone"] = body.phone
    if body.birth_date is not None:
        updates["birth_date"] = body.birth_date

    if updates:
        await repos.users.update(current_user.id, updates)
        await db.commit()
        await db.refresh(current_user)
    return current_user

# Belirtilen kullanicinin temel profil kaydini getirir.
@router.get("/{user_id}", response_model=UserResponse)
async def get_user_profile(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    """Yetkili kullanıcı için kullanıcı okuma isteğini işler."""
    user = await repos.users.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user
