from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from app.core.supabase import get_supabase
from app.services.ai_service import call_ai, get_usage_stats
import json

router = APIRouter()


@router.get("/{session_id}")
async def generate_report(session_id: str, use_ai: bool = True):
    """
    Generate laporan hasil scan.
    use_ai=True  → AI buat ringkasan naratif (butuh token)
    use_ai=False → Laporan struktural tanpa AI (gratis)
    """
    db = get_supabase()

    session = db.table("scan_session").select("*, target(nama, base_url)").eq("id", session_id).single().execute()
    if not session.data:
        raise HTTPException(404, "Session tidak ditemukan")

    results = db.table("test_result").select("*").eq("session_id", session_id).execute()

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
        "findings_by_severity": by_severity,
        "total_findings": len(results.data),
        "ai_summary": None,
    }

    if use_ai and results.data:
        prompt = (
            f"Buat ringkasan eksekutif bug bounty report untuk target: "
            f"{session.data.get('target', {}).get('base_url', '')}.\n"
            f"Temuan:\n{json.dumps(by_severity, indent=2)}\n"
            "Format: paragraf singkat, highlight risiko tertinggi, rekomendasi remediasi."
        )
        report["ai_summary"] = await call_ai(prompt)
        report["ai_usage"] = get_usage_stats()

    return report
