from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import User
from repositories.factory import RepoSet
from routers.deps import get_current_user, get_repo_set
from schemas import ClinicalNoteCreate, ClinicalNoteResponse, ClinicalNoteUpdate

router = APIRouter(prefix="/clinical-notes", tags=["clinical-notes"])

@router.post("", response_model=ClinicalNoteResponse, status_code=201)
async def create_note(
    body: ClinicalNoteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    if current_user.role != "DOCTOR":
        raise HTTPException(status_code=403, detail="Only DOCTOR users can create notes")

    link = await repos.relations.find_active_link(body.patient_id, current_user.id)
    if link is None:
        raise HTTPException(status_code=403, detail="Not linked to this patient")

    note_data = {
        "id": str(uuid4()),
        "doctor_id": current_user.id,
        "patient_id": body.patient_id,
        "note": body.note,
        "recommendation": body.recommendation,
    }
    result = await repos.clinical_notes.create(note_data)
    await db.commit()
    return result

@router.get("/{patient_id}", response_model=list[ClinicalNoteResponse])
async def get_notes_for_patient(
    patient_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    if current_user.role == "DOCTOR":
        return await repos.clinical_notes.list_by_patient(patient_id, doctor_id=current_user.id)
    elif current_user.role == "SELF" and current_user.id == patient_id:
        return await repos.clinical_notes.list_by_patient(patient_id)
    else:
        raise HTTPException(status_code=403, detail="Access denied")

@router.put("/{note_id}", response_model=ClinicalNoteResponse)
async def update_note(
    note_id: str,
    body: ClinicalNoteUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    existing = await repos.clinical_notes.get_by_id(note_id)
    if existing is None or existing.get("doctor_id") != current_user.id:
        raise HTTPException(status_code=404, detail="Note not found")

    updates = {"updated_at": datetime.utcnow()}
    if body.note is not None:
        updates["note"] = body.note
    if body.recommendation is not None:
        updates["recommendation"] = body.recommendation

    result = await repos.clinical_notes.update(note_id, updates)
    await db.commit()
    return result

@router.delete("/{note_id}", status_code=204)
async def delete_note(
    note_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    repos: RepoSet = Depends(get_repo_set),
):
    existing = await repos.clinical_notes.get_by_id(note_id)
    if existing is None or existing.get("doctor_id") != current_user.id:
        raise HTTPException(status_code=404, detail="Note not found")
    await repos.clinical_notes.delete(note_id)
    await db.commit()
