from fastapi import APIRouter, HTTPException
from app.core.supabase import get_supabase

router = APIRouter()


@router.get("/{session_id}")
def get_results(session_id: str, severity: str = None):
    """Ambil semua temuan dari satu session. Filter opsional by severity."""
    db = get_supabase()
    q = db.table("test_result").select("*, hack_methods(nama, domain_kategori)").eq("session_id", session_id)
    if severity:
        q = q.eq("severity", severity)
    res = q.order("created_at", desc=True).execute()
    return res.data


@router.get("/summary/{session_id}")
def get_summary(session_id: str):
    """Ringkasan temuan per severity untuk satu session."""
    db = get_supabase()
    results = db.table("test_result").select("severity, status").eq("session_id", session_id).execute()

    summary: dict = {}
    for r in results.data:
        sev = r.get("severity") or "unknown"
        summary[sev] = summary.get(sev, 0) + 1

    return {"session_id": session_id, "by_severity": summary, "total": len(results.data)}
