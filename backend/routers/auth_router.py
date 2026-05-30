from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4

from auth import create_access_token, hash_password, verify_password
from database import get_db
from models import User
from repositories.factory import RepoSet
from routers.deps import get_current_user, get_repo_set
from schemas import LoginRequest, RegisterRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])

# Yeni kullanici olusturup erisim tokeni dondurur.
@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
    repos: RepoSet = Depends(get_repo_set),
):
    """Kimlik doğrulama oluşturma isteğini doğrulayıp kaydeder."""
    existing = await repos.users.get_by_email(body.email.lower())
    if existing is not None:
        raise HTTPException(status_code=400, detail="Email already registered")

    user_id = str(uuid4())
    user_data = {
        "id": user_id,
        "email": body.email.lower().strip(),
        "password_hash": hash_password(body.password),
        "role": body.role,
        "full_name": body.full_name.strip(),
        "phone": body.phone,
        "birth_date": body.birth_date,
    }
    await repos.users.create(user_data)
    await repos.app_settings.get_or_create(user_id)
    if body.role == "SELF":
        await repos.simulation.get_or_create(user_id)

    await db.commit()

    token = create_access_token({"sub": user_id, "role": body.role})
    return TokenResponse(
        access_token=token,
        user_id=user_id,
        role=body.role,
        full_name=body.full_name.strip(),
    )

# E-posta ve parola ile giris yapip erisim tokeni dondurur.
@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
    repos: RepoSet = Depends(get_repo_set),
):
    """Kimlik doğrulama endpoint isteğini doğrulayıp ilgili katmana yönlendirir."""
    user = await repos.users.get_by_email(body.email.lower())
    if user is None or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token({"sub": user["id"], "role": user["role"]})
    return TokenResponse(
        access_token=token,
        user_id=user["id"],
        role=user["role"],
        full_name=user["full_name"],
    )
