"""
app/routers/targets.py
----------------------
CRUD untuk target dan endpoint-nya.
Semua operasi terisolasi per user via user_id filter + RLS Supabase.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, HttpUrl

from app.core.auth import CurrentUser
from app.core.supabase import get_supabase

router = APIRouter(prefix="/api/targets", tags=["Targets"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class TargetCreate(BaseModel):
    nama:     str
    jenis:    str        # web | api | mobile | network | other
    base_url: str
    deskripsi: str | None = None


class EndpointCreate(BaseModel):
    path:      str
    method:    str = "GET"
    deskripsi: str | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_target_or_404(target_id: str, user_id: str) -> dict:
    """Ambil target milik user. Return 404 jika tidak ada atau bukan miliknya."""
    sb     = get_supabase()
    result = (
        sb.table("target")
        .select("*")
        .eq("id", target_id)
        .eq("user_id", user_id)
        .eq("is_active", True)
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Target tidak ditemukan.")
    return result.data


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
def list_targets(user: CurrentUser):
    """List semua target aktif milik user yang sedang login."""
    sb = get_supabase()
    result = (
        sb.table("target")
        .select("id, nama, jenis, base_url, deskripsi, is_active, created_at")
        .eq("user_id", user.user_id)
        .eq("is_active", True)
        .order("created_at", desc=True)
        .execute()
    )
    return {"message": "OK", "data": result.data}


@router.post("", status_code=201)
def create_target(body: TargetCreate, user: CurrentUser):
    """Buat target baru. user_id otomatis dari JWT."""
    sb = get_supabase()
    result = (
        sb.table("target")
        .insert({
            "nama":     body.nama,
            "jenis":    body.jenis,
            "base_url": body.base_url,
            "deskripsi": body.deskripsi or "",
            "user_id":  user.user_id,
        })
        .execute()
    )
    return {"message": "Target berhasil dibuat.", "data": result.data[0]}


@router.get("/{target_id}")
def get_target(target_id: str, user: CurrentUser):
    """Detail target beserta endpoint-nya."""
    sb     = get_supabase()
    target = _get_target_or_404(target_id, user.user_id)

    endpoints = (
        sb.table("target_endpoint")
        .select("id, path, method, deskripsi, is_active")
        .eq("target_id", target_id)
        .eq("is_active", True)
        .execute()
    )
    target["endpoints"] = endpoints.data
    return {"message": "OK", "data": target}


@router.put("/{target_id}")
def update_target(target_id: str, body: TargetCreate, user: CurrentUser):
    """Update target. Hanya milik user sendiri."""
    _get_target_or_404(target_id, user.user_id)
    sb = get_supabase()
    result = (
        sb.table("target")
        .update({
            "nama":      body.nama,
            "jenis":     body.jenis,
            "base_url":  body.base_url,
            "deskripsi": body.deskripsi or "",
        })
        .eq("id", target_id)
        .execute()
    )
    return {"message": "Target berhasil diupdate.", "data": result.data[0]}


@router.delete("/{target_id}")
def delete_target(target_id: str, user: CurrentUser):
    """Soft delete target (is_active = false)."""
    _get_target_or_404(target_id, user.user_id)
    sb = get_supabase()
    sb.table("target").update({"is_active": False}).eq("id", target_id).execute()
    return {"message": "Target berhasil dihapus.", "data": {"id": target_id}}


@router.post("/{target_id}/endpoints", status_code=201)
def add_endpoint(target_id: str, body: EndpointCreate, user: CurrentUser):
    """Tambah endpoint ke target milik user."""
    _get_target_or_404(target_id, user.user_id)
    sb = get_supabase()
    result = (
        sb.table("target_endpoint")
        .insert({
            "target_id": target_id,
            "path":      body.path,
            "method":    body.method,
            "deskripsi": body.deskripsi or "",
        })
        .execute()
    )
    return {"message": "Endpoint berhasil ditambahkan.", "data": result.data[0]}


@router.delete("/{target_id}/endpoints/{endpoint_id}")
def delete_endpoint(target_id: str, endpoint_id: str, user: CurrentUser):
    """Soft delete endpoint."""
    _get_target_or_404(target_id, user.user_id)
    sb = get_supabase()
    sb.table("target_endpoint").update({"is_active": False}).eq("id", endpoint_id).execute()
    return {"message": "Endpoint berhasil dihapus.", "data": {"id": endpoint_id}}
