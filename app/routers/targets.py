"""
app/routers/targets.py (PATCHED — multi-tenant)
------------------------------------------------
Perubahan dari versi lama:
- Semua endpoint wajib login via Depends(get_current_user)
- create_target otomatis inject user_id dari JWT
- list/get/delete hanya return data milik user yang sedang login
- Operasi ke user lain → 404 (bukan 403, agar tidak expose keberadaan resource)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.agent.repository import ScanRepository
from app.api.dependencies import get_repository
from app.api.schemas import (
    TargetCreate, EndpointCreate, MessageResponse,
)
from app.core.auth import CurrentUser

router = APIRouter(prefix="/api/targets", tags=["Targets"])


@router.post("", response_model=MessageResponse, status_code=201)
def create_target(
    body: TargetCreate,
    current_user: CurrentUser,
    repo: ScanRepository = Depends(get_repository),
):
    """Buat target baru. user_id otomatis dari JWT."""
    target = repo.create_target(
        nama      = body.nama,
        jenis     = body.jenis,
        base_url  = body.base_url,
        deskripsi = body.deskripsi,
        user_id   = current_user.user_id,  # ← inject dari auth
    )
    return MessageResponse(message="Target berhasil dibuat.", data=target)


@router.get("", response_model=MessageResponse)
def list_targets(
    current_user: CurrentUser,
    repo: ScanRepository = Depends(get_repository),
):
    """List semua target aktif milik user yang sedang login."""
    result = (
        repo.sb.table("target")
        .select("id, nama, jenis, base_url, deskripsi, is_active, created_at")
        .eq("user_id", current_user.user_id)   # ← filter by user
        .eq("is_active", True)
        .order("created_at", desc=True)
        .execute()
    )
    return MessageResponse(message="OK", data=result.data)


@router.get("/{target_id}", response_model=MessageResponse)
def get_target(
    target_id: str,
    current_user: CurrentUser,
    repo: ScanRepository = Depends(get_repository),
):
    """Detail satu target beserta endpoint-nya. Hanya milik user sendiri."""
    target = repo.get_target(target_id, user_id=current_user.user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Target tidak ditemukan.")

    endpoints = repo.get_target_endpoints(target_id)
    target["endpoints"] = endpoints
    return MessageResponse(message="OK", data=target)


@router.delete("/{target_id}", response_model=MessageResponse)
def delete_target(
    target_id: str,
    current_user: CurrentUser,
    repo: ScanRepository = Depends(get_repository),
):
    """Soft delete target (set is_active=False). Hanya milik user sendiri."""
    target = repo.get_target(target_id, user_id=current_user.user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Target tidak ditemukan.")

    repo.sb.table("target").update({"is_active": False}).eq("id", target_id).execute()
    return MessageResponse(message="Target berhasil dihapus.", data={"id": target_id})


@router.post("/{target_id}/endpoints", response_model=MessageResponse, status_code=201)
def add_endpoint(
    target_id: str,
    body: EndpointCreate,
    current_user: CurrentUser,
    repo: ScanRepository = Depends(get_repository),
):
    """Tambah endpoint ke target. Verifikasi kepemilikan target dulu."""
    # Pastikan target ini milik user yang sedang login
    target = repo.get_target(target_id, user_id=current_user.user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Target tidak ditemukan.")

    result = (
        repo.sb.table("target_endpoint")
        .insert({
            "target_id": target_id,
            "path":      body.path,
            "method":    body.method,
            "deskripsi": body.deskripsi,
        })
        .execute()
    )
    return MessageResponse(message="Endpoint berhasil ditambahkan.", data=result.data[0])
