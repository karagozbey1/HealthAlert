from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import decode_token
from database import get_db
from models import User
from repositories.factory import RepoSet, get_repos

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# JWT tokenını doğrular ve mevcut kullanıcıyı döndürür.
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id: str | None = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bad token payload")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user

# Aktif DATA_MODE için RepoSet döndüren FastAPI dependency.
async def get_repo_set(db: AsyncSession = Depends(get_db)) -> RepoSet:
    return get_repos(db=db)
