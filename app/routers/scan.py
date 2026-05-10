from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
import uuid
from datetime import datetime, timezone
from app.core.supabase import get_supabase
from app.services.scan_service import run_full_scan
from app.services.ai_service import triage_findings, get_usage_stats

router = APIRouter()


class ScanRequest(BaseModel):
    target_id: str
    session_name: str = ""
    severity_filter: str = "medium,high,critical"  # filter nuclei
    use_ai_triage: bool = True


@router.post("/start")
async def start_scan(body: ScanRequest, bg: BackgroundTasks):
    """
    Mulai scan otomatis: subfinder → httpx → nuclei.
    Berjalan sebagai background task, langsung return session_id.
    """
    db = get_supabase()

    # Ambil data target
    target = db.table("target").select("*").eq("id", body.target_id).single().execute()
    if not target.data:
        raise HTTPException(404, "Target tidak ditemukan")

    # Ambil method_id default (atau bisa dikirim dari client)
    method = db.table("hack_methods").select("id").eq("is_active", True).limit(1).execute()
    method_id = method.data[0]["id"] if method.data else str(uuid.uuid4())

    # Buat scan session baru
    session_id = str(uuid.uuid4())
    db.table("scan_session").insert({
        "id": session_id,
        "target_id": body.target_id,
        "nama": body.session_name or f"Scan {target.data['nama']} {datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}",
        "status": "pending",
    }).execute()

    # Jalankan scan di background
    bg.add_task(
        run_full_scan,
        session_id=session_id,
        target_id=body.target_id,
        base_url=target.data["base_url"],
        method_id=method_id,
    )

    return {
        "session_id": session_id,
        "status": "pending",
        "message": "Scan dimulai, pantau via GET /api/scan/status/{session_id}",
    }


@router.get("/status/{session_id}")
async def get_scan_status(session_id: str):
    """Cek status scan session + jumlah temuan saat ini."""
    db = get_supabase()
    session = db.table("scan_session").select("*").eq("id", session_id).single().execute()
    if not session.data:
        raise HTTPException(404, "Session tidak ditemukan")

    count = db.table("test_result").select("id", count="exact").eq("session_id", session_id).execute()

    return {
        **session.data,
        "total_findings": count.count or 0,
    }


@router.post("/triage/{session_id}")
async def triage_session(session_id: str):
    """
    Kirim temuan session ke AI untuk triage.
    Mematuhi batas ai_max_findings_per_call dari config.
    """
    db = get_supabase()
    results = db.table("test_result").select("*").eq("session_id", session_id).execute()
    if not results.data:
        raise HTTPException(404, "Belum ada temuan untuk session ini")

    triage = await triage_findings(results.data)
    usage  = get_usage_stats()

    return {
        "session_id": session_id,
        "triage": triage,
        "ai_usage": usage,
    }
