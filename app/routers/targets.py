from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Literal
import uuid
from datetime import datetime, timezone
from app.core.supabase import get_supabase

router = APIRouter()


class TargetCreate(BaseModel):
    nama: str
    jenis: Literal["web", "api", "mobile", "network", "other"]
    base_url: str
    deskripsi: Optional[str] = None


class EndpointCreate(BaseModel):
    target_id: str
    path: str
    method: Literal["GET","POST","PUT","PATCH","DELETE","HEAD","OPTIONS"] = "GET"
    deskripsi: Optional[str] = None


@router.get("/")
def list_targets():
    db = get_supabase()
    res = db.table("target").select("*").eq("is_active", True).order("created_at", desc=True).execute()
    return res.data


@router.post("/")
def create_target(body: TargetCreate):
    db = get_supabase()
    now = datetime.now(timezone.utc).isoformat()
    res = db.table("target").insert({
        "id": str(uuid.uuid4()),
        "nama": body.nama,
        "jenis": body.jenis,
        "base_url": body.base_url,
        "deskripsi": body.deskripsi,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }).execute()
    return res.data[0]


@router.delete("/{target_id}")
def deactivate_target(target_id: str):
    db = get_supabase()
    db.table("target").update({"is_active": False}).eq("id", target_id).execute()
    return {"message": "Target dinonaktifkan"}


@router.post("/endpoints")
def add_endpoint(body: EndpointCreate):
    db = get_supabase()
    res = db.table("target_endpoint").insert({
        "id": str(uuid.uuid4()),
        "target_id": body.target_id,
        "path": body.path,
        "method": body.method,
        "deskripsi": body.deskripsi,
    }).execute()
    return res.data[0]


@router.get("/{target_id}/endpoints")
def list_endpoints(target_id: str):
    db = get_supabase()
    res = db.table("target_endpoint").select("*").eq("target_id", target_id).execute()
    return res.data
