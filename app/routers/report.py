from fastapi import APIRouter, HTTPException
from app.core.supabase import get_supabase
from app.services.ai_service import generate_ai_report_summary, get_usage_stats

router = APIRouter()


@router.get("/{session_id}")
async def generate_report(session_id: str, use_ai: bool = True):
    """
    Generate laporan hasil scan.

    use_ai=True  → AI buat ringkasan naratif (data sensitif otomatis di-strip sebelum dikirim)
    use_ai=False → Laporan struktural tanpa AI, semua data asli tersedia untuk review internal
    """
    db = get_supabase()

    session = db.table("scan_session").select("*, target(nama, base_url, jenis)").eq("id", session_id).single().execute()
    if not session.data:
        raise HTTPException(404, "Session tidak ditemukan")

    results = db.table("test_result").select("*").eq("session_id", session_id).execute()

    # Grouping per severity — data LENGKAP untuk laporan internal
    by_severity: dict = {}
    for r in results.data:
        sev = r.get("severity") or "unknown"
        by_severity.setdefault(sev, []).append(r.get("finding", ""))

    report = {
        "session_id": session_id,
        "target": session.data.get("target", {}),
        "status": session.data.get("status"),
        "started_at": session.data.get("started_at"),
        "finished_at": session.data.get("finished_at"),
        "findings_by_severity": by_severity,   # data lengkap — hanya untuk internal
        "total_findings": len(results.data),
        "ai_summary": None,
        "data_privacy_note": (
            "Data sensitif (IP, URL, token, credential) tidak dikirim ke AI. "
            "AI hanya menerima pola vulnerability untuk triage."
        ),
    }

    if use_ai and results.data:
        target_info = session.data.get("target", {})
        # generate_ai_report_summary sudah sanitasi otomatis di dalam
        report["ai_summary"] = await generate_ai_report_summary(target_info, by_severity)
        report["ai_usage"] = get_usage_stats()

    return report