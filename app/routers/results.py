"""
app/routers/results.py
----------------------
Ambil hasil test dari sebuah scan session.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.auth import CurrentUser
from app.core.supabase import get_supabase

router = APIRouter(prefix="/api/results", tags=["Results"])


def _verify_session_ownership(session_id: str, user_id: str) -> None:
    """Pastikan session milik user. Raise 404 jika tidak."""
    sb     = get_supabase()
    result = (
        sb.table("scan_session")
        .select("id")
        .eq("id", session_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Session tidak ditemukan.")


@router.get("/{session_id}")
def get_results(session_id: str, user: CurrentUser):
    """
    Ambil semua hasil test dari session.
    Include nama method dan path endpoint via join.
    """
    _verify_session_ownership(session_id, user.user_id)

    sb     = get_supabase()
    result = (
        sb.table("test_result")
        .select(
            "id, status, severity, finding, raw_output, created_at, "
            "hack_methods(nama, domain_kategori, risk_level, execution_mode), "
            "target_endpoint(path, method)"
        )
        .eq("session_id", session_id)
        .order("created_at")
        .execute()
    )
    return {"message": "OK", "data": result.data, "total": len(result.data)}


@router.get("/{session_id}/findings")
def get_findings(session_id: str, user: CurrentUser, severity: str | None = None):
    """
    Ambil hanya hasil dengan status 'fail' (vulnerability ditemukan).
    Optional filter by severity: critical | high | medium | low | info
    """
    _verify_session_ownership(session_id, user.user_id)

    sb    = get_supabase()
    query = (
        sb.table("test_result")
        .select(
            "id, severity, finding, raw_output, created_at, "
            "hack_methods(nama, domain_kategori, risk_level), "
            "target_endpoint(path, method)"
        )
        .eq("session_id", session_id)
        .eq("status", "fail")
        .order("created_at")
    )
    if severity:
        query = query.eq("severity", severity)

    result = query.execute()
    return {"message": "OK", "data": result.data, "total": len(result.data)}


@router.get("/{session_id}/summary")
def get_summary(session_id: str, user: CurrentUser):
    """Ringkasan statistik hasil scan."""
    _verify_session_ownership(session_id, user.user_id)

    sb     = get_supabase()
    result = (
        sb.table("test_result")
        .select("status, severity, finding, hack_methods(nama, domain_kategori)")
        .eq("session_id", session_id)
        .execute()
    )
    rows = result.data

    summary  = {"total": len(rows), "pass": 0, "fail": 0, "error": 0, "skipped": 0}
    severity = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    findings = []

    for r in rows:
        summary[r["status"]] = summary.get(r["status"], 0) + 1
        if r["status"] == "fail" and r.get("severity"):
            severity[r["severity"]] = severity.get(r["severity"], 0) + 1
            findings.append({
                "method":   (r.get("hack_methods") or {}).get("nama", "-"),
                "category": (r.get("hack_methods") or {}).get("domain_kategori", "-"),
                "severity": r["severity"],
                "finding":  r["finding"],
            })

    return {
        "message": "OK",
        "data": {
            "counts":   summary,
            "severity": severity,
            "findings": findings,
        }
    }
