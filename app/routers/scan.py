"""
app/routers/scan.py
-------------------
Trigger scan dan cek status.
Scan berjalan di background task — langsung return session_id.
Subscribe /ws/{session_id} untuk real-time progress (jika WebSocket tersedia).
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from app.core.auth import CurrentUser
from app.core.supabase import get_supabase
from app.services.scan_service import run_scan_session

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/scan", tags=["Scan"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class ScanRequest(BaseModel):
    target_id:      str | None = None   # UUID target yang sudah ada
    manual_url:     str | None = None   # Atau URL langsung (auto-create target)
    session_nama:   str | None = None
    execution_mode: str = "passive"     # passive | active | hybrid
    use_ai_triage:  bool = True
    timeout:        int = 30


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_target_or_404(target_id: str, user_id: str) -> dict:
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


def _create_target(base_url: str, user_id: str) -> dict:
    hostname = urlparse(base_url).hostname or base_url
    sb       = get_supabase()
    result   = (
        sb.table("target")
        .insert({
            "nama":     f"[Manual] {hostname}",
            "jenis":    "web",
            "base_url": base_url,
            "deskripsi": "Auto-created dari manual URL.",
            "user_id":  user_id,
        })
        .execute()
    )
    return result.data[0]


def _create_session(target_id: str, user_id: str, nama: str | None) -> dict:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    sb  = get_supabase()
    result = (
        sb.table("scan_session")
        .insert({
            "target_id":  target_id,
            "user_id":    user_id,
            "nama":       nama,
            "status":     "running",
            "started_at": now,
        })
        .execute()
    )
    return result.data[0]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/start", status_code=202)
async def start_scan(
    body: ScanRequest,
    background_tasks: BackgroundTasks,
    user: CurrentUser,
):
    """
    Mulai scan (202 Accepted).
    Scan berjalan di background — polling /api/scan/status/{session_id}.
    """
    if not body.target_id and not body.manual_url:
        raise HTTPException(
            status_code=422,
            detail="Wajib isi salah satu: target_id atau manual_url.",
        )

    # Resolve target
    if body.target_id:
        target   = _get_target_or_404(body.target_id, user.user_id)
        base_url = target["base_url"]
    else:
        target   = _create_target(body.manual_url, user.user_id)  # type: ignore[arg-type]
        base_url = body.manual_url

    target_id  = target["id"]
    session    = _create_session(
        target_id  = target_id,
        user_id    = user.user_id,
        nama       = body.session_nama or f"Scan — {base_url}",
    )
    session_id = session["id"]

    background_tasks.add_task(
        run_scan_session,
        session_id     = session_id,
        target_id      = target_id,
        base_url       = base_url,
        execution_mode = body.execution_mode,
        use_ai_triage  = body.use_ai_triage,
        timeout        = body.timeout,
    )

    logger.info("Scan started: session=%s target=%s user=%s", session_id, target_id, user.user_id[:8])

    return {
        "message":    "Scan dimulai. Poll status di endpoint di bawah.",
        "data": {
            "session_id": session_id,
            "target_url": base_url,
            "status_url": f"/api/scan/status/{session_id}",
        }
    }


@router.get("/status/{session_id}")
def scan_status(session_id: str, user: CurrentUser):
    """Cek status scan. Hanya bisa akses session milik sendiri."""
    sb     = get_supabase()
    result = (
        sb.table("scan_session")
        .select("id, nama, status, started_at, finished_at, notes")
        .eq("id", session_id)
        .eq("user_id", user.user_id)
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Session tidak ditemukan.")

    session = result.data

    # Jika selesai, tambahkan ringkasan hasil
    if session["status"] in ("completed", "failed"):
        counts = (
            sb.table("test_result")
            .select("status, severity")
            .eq("session_id", session_id)
            .execute()
        )
        rows     = counts.data
        summary  = {"total": len(rows), "pass": 0, "fail": 0, "error": 0, "skipped": 0}
        severity = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
        for r in rows:
            summary[r["status"]] = summary.get(r["status"], 0) + 1
            if r.get("severity"):
                severity[r["severity"]] = severity.get(r["severity"], 0) + 1
        session["summary"]  = summary
        session["severity"] = severity

    return {"message": "OK", "data": session}


@router.post("/triage/{session_id}")
def triage_session(session_id: str, user: CurrentUser):
    """Jalankan AI triage pada hasil scan yang sudah selesai."""
    from app.services.ai_service import run_triage
    sb     = get_supabase()
    result = (
        sb.table("scan_session")
        .select("id, status")
        .eq("id", session_id)
        .eq("user_id", user.user_id)
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Session tidak ditemukan.")
    if result.data["status"] != "completed":
        raise HTTPException(status_code=400, detail="Scan belum selesai.")

    analysis = run_triage(session_id)
    return {"message": "Triage selesai.", "data": {"analysis": analysis}}
