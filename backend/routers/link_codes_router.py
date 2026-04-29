from __future__ import annotations

import random
import string
from datetime import datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from models import User
from repositories.factory import RepoSet
from routers.deps import get_current_user, get_repo_set
from schemas import (
    LinkCodeGenerateRequest,
    LinkCodeResponse,
    RedeemCodeRequest,
    RedeemCodeResponse,
    UserRelationResponse,
)

router = APIRouter(prefix="/link-codes", tags=["link-codes"])

def _generate_numeric_code(length: int = 6) -> str:
    return "".join(random.choices(string.digits, k=length))

async def _unique_code(repos: RepoSet) -> str:
    for _ in range(20):
        code = _generate_numeric_code(6)
        existing = await repos.link_codes.get_by_code(code)
        if existing is None:
            return code
    raise RuntimeError("Could not generate unique code after 20 attempts")

@router.post("/generate", response_model=LinkCodeResponse, status_code=201)
async def generate_code(
    body: LinkCodeGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    if current_user.role != "SELF":
        raise HTTPException(status_code=403, detail="Sadece SELF kullanicisi kod uretebilir")

    relation_type = body.relation_type.upper()
    if relation_type not in ("RELATIVE", "DOCTOR"):
        raise HTTPException(status_code=400, detail="relation_type RELATIVE veya DOCTOR olmali")

    code_str = await _unique_code(repos)
    code_data = {
        "id": str(uuid4()),
        "code": code_str,
        "owner_id": current_user.id,
        "code_type": relation_type,
        "is_active": True,
        "uses_remaining": settings.LINK_CODE_USES,
        "expires_at": datetime.utcnow() + timedelta(hours=settings.LINK_CODE_EXPIRE_HOURS),
    }
    result = await repos.link_codes.create(code_data)
    await db.commit()
    return result

@router.get("/mine", response_model=list[LinkCodeResponse])
async def get_my_codes(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    return await repos.link_codes.list_by_owner(current_user.id)

@router.delete("/{code_id}", status_code=204)
async def revoke_code(
    code_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    code = await repos.link_codes.get_by_id(code_id)
    if code is None or code["owner_id"] != current_user.id:
        raise HTTPException(status_code=404, detail="Code not found")
    await repos.link_codes.update(code_id, {"is_active": False, "uses_remaining": 0})
    await db.commit()

@router.post("/redeem", response_model=RedeemCodeResponse, status_code=201)
async def redeem_code(
    body: RedeemCodeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    if current_user.role not in ("RELATIVE", "DOCTOR"):
        raise HTTPException(status_code=403, detail="Sadece RELATIVE veya DOCTOR kullanicisi kod girebilir")

    code = await repos.link_codes.get_by_code(body.code.strip())
    if code is None:
        raise HTTPException(status_code=404, detail="Gecersiz kod")
    if not code["is_active"]:
        raise HTTPException(status_code=400, detail="Kod artik aktif degil")
    if code["expires_at"] < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Kodun suresi dolmus")
    if code["uses_remaining"] <= 0:
        raise HTTPException(status_code=400, detail="Kod kullanim hakki bitmis")
    if code["owner_id"] == current_user.id:
        raise HTTPException(status_code=400, detail="Kendi kodunuzu kullanamazsiniz")

    owner = await repos.users.get_by_id(code["owner_id"])
    if owner is None or owner.get("role") != "SELF":
        raise HTTPException(status_code=400, detail="Kod sahibi SELF olmali")

    if current_user.role != code["code_type"]:
        raise HTTPException(status_code=400, detail="Bu kod sizin rolunuz icin degil")

    existing_link = await repos.relations.find_active_link(code["owner_id"], current_user.id)
    if existing_link is not None:
        raise HTTPException(status_code=400, detail="Bu kisiyle zaten baglantiniz var")
    reverse_link = await repos.relations.find_active_link(current_user.id, code["owner_id"])
    if reverse_link is not None:
        raise HTTPException(status_code=400, detail="Bu kisiyle zaten baglantiniz var")

    relation_id = str(uuid4())
    relation_data = {
        "id": relation_id,
        "self_user_id": code["owner_id"],
        "linked_user_id": current_user.id,
        "relation_type": current_user.role,
        "is_active": True,
    }
    await repos.relations.create(relation_data)

    new_uses = code["uses_remaining"] - 1
    code_updates = {"uses_remaining": new_uses}
    if new_uses <= 0:
        code_updates["is_active"] = False
    await repos.link_codes.update(code["id"], code_updates)

    await repos.notifications.create({
        "id": str(uuid4()),
        "recipient_id": code["owner_id"],
        "sender_id": current_user.id,
        "title": "Yeni Bağlantı Kuruldu",
        "body": f"{current_user.full_name} kodunuzu kullanarak hesabiniza baglandi.",
        "notification_type": "link",
        "reference_id": relation_id,
        "reference_type": "relation",
        "is_read": False,
    })
    await repos.history.create({
        "id": str(uuid4()),
        "user_id": current_user.id,
        "item_type": "link",
        "title": "Yeni bağlantı kuruldu",
        "subtitle": f"{owner['full_name'] if owner else 'Asil kisi'} hesabina baglanti saglandi",
        "severity": "normal",
    })

    await db.commit()

    return RedeemCodeResponse(
        relation_id=relation_id,
        self_user_id=code["owner_id"],
        linked_user_id=current_user.id,
        relation_type=current_user.role,
        linked_user_name=owner["full_name"] if owner else "Unknown",
    )

@router.get("/relations", response_model=list[UserRelationResponse])
async def get_my_relations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    if current_user.role == "SELF":
        relations = await repos.relations.find_active_by_self_user(current_user.id)
        out = []
        for rel in relations:
            user = await repos.users.get_by_id(rel["linked_user_id"])
            out.append(UserRelationResponse(
                id=rel["id"],
                self_user_id=rel["self_user_id"],
                linked_user_id=rel["linked_user_id"],
                relation_type=rel["relation_type"],
                is_active=rel["is_active"],
                linked_user_name=user["full_name"] if user else "Unknown",
                created_at=rel["created_at"],
            ))
        return out
    else:
        relations = await repos.relations.find_active_by_linked_user(current_user.id)
        out = []
        for rel in relations:
            user = await repos.users.get_by_id(rel["self_user_id"])
            out.append(UserRelationResponse(
                id=rel["id"],
                self_user_id=rel["self_user_id"],
                linked_user_id=rel["linked_user_id"],
                relation_type=rel["relation_type"],
                is_active=rel["is_active"],
                linked_user_name=user["full_name"] if user else "Unknown",
                created_at=rel["created_at"],
            ))
        return out

@router.delete("/relations/{relation_id}", status_code=204)
async def remove_relation(
    relation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    rel = await repos.relations.get_by_id(relation_id)
    if rel is None:
        raise HTTPException(status_code=404, detail="Relation not found")
    if rel["self_user_id"] != current_user.id and rel["linked_user_id"] != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    await repos.relations.update(relation_id, {"is_active": False, "revoked_at": datetime.utcnow()})
    await db.commit()
