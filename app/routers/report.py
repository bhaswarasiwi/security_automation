"""
app/routers/report.py
---------------------
Generate laporan scan dalam format Markdown.
Opsional: analisis AI untuk triage dan rekomendasi.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException

from app.core.auth import CurrentUser
from app.core.supabase import get_supabase

router = APIRouter(prefix="/api/report", tags=["Report"])


@router.get("/{session_id}")
def generate_report(
    session_id: str,
    user:       CurrentUser,
    use_ai:     bool = True,
):
    """
    Generate laporan lengkap untuk satu scan session.
    use_ai=true → tambahkan analisis AI triage.
    """
    sb = get_supabase()

    # Verifikasi kepemilikan dan ambil session
    session_res = (
        sb.table("scan_session")
        .select("*, target(nama, base_url, jenis)")
        .eq("id", session_id)
        .eq("user_id", user.user_id)
        .maybe_single()
        .execute()
    )
    if not session_res.data:
        raise HTTPException(status_code=404, detail="Session tidak ditemukan.")

    session = session_res.data
    if session["status"] not in ("completed", "failed"):
        raise HTTPException(status_code=400, detail="Scan belum selesai.")

    # Ambil semua hasil
    results_res = (
        sb.table("test_result")
        .select(
            "status, severity, finding, created_at, "
            "hack_methods(nama, domain_kategori, risk_level), "
            "target_endpoint(path, method)"
        )
        .eq("session_id", session_id)
        .order("created_at")
        .execute()
    )
    rows = results_res.data

    # Hitung statistik
    stats    = {"total": len(rows), "pass": 0, "fail": 0, "error": 0, "skipped": 0}
    severity = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    findings = []

    for r in rows:
        stats[r["status"]] = stats.get(r["status"], 0) + 1
        if r["status"] == "fail" and r.get("severity"):
            severity[r["severity"]] = severity.get(r["severity"], 0) + 1
            findings.append({
                "method":   (r.get("hack_methods") or {}).get("nama", "-"),
                "severity": r["severity"],
                "finding":  r["finding"],
            })

    # Build Markdown report
    target   = session.get("target") or {}
    now      = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    md_lines = [
        f"# Security Scan Report",
        f"",
        f"**Target**: {target.get('nama', '-')} — `{target.get('base_url', '-')}`",
        f"**Jenis**: {target.get('jenis', '-')}",
        f"**Session**: `{session_id}`",
        f"**Status**: {session['status']}",
        f"**Mulai**: {session.get('started_at', '-')}",
        f"**Selesai**: {session.get('finished_at', '-')}",
        f"**Dibuat**: {now}",
        f"",
        f"---",
        f"",
        f"## Ringkasan",
        f"",
        f"| Metrik | Nilai |",
        f"|--------|-------|",
        f"| Total test | {stats['total']} |",
        f"| Pass | {stats['pass']} |",
        f"| Fail (vulnerability) | {stats['fail']} |",
        f"| Error | {stats['error']} |",
        f"| Skipped | {stats['skipped']} |",
        f"",
        f"### Distribusi Severity",
        f"",
        f"| Severity | Jumlah |",
        f"|----------|--------|",
    ]
    for sev in ["critical", "high", "medium", "low", "info"]:
        md_lines.append(f"| {sev.capitalize()} | {severity[sev]} |")

    if findings:
        md_lines += [
            f"",
            f"---",
            f"",
            f"## Temuan Vulnerability ({len(findings)})",
            f"",
        ]
        for i, f in enumerate(findings, 1):
            md_lines += [
                f"### {i}. [{f['severity'].upper()}] {f['method']}",
                f"",
                f"{f['finding']}",
                f"",
            ]

    # AI triage (opsional)
    ai_analysis = None
    if use_ai and findings:
        try:
            from app.services.ai_service import run_triage
            ai_analysis = run_triage(session_id)
            md_lines += [
                f"---",
                f"",
                f"## Analisis AI",
                f"",
                ai_analysis,
                f"",
            ]
        except Exception as e:
            md_lines += [f"", f"*AI triage tidak tersedia: {e}*", f""]

    report_md = "\n".join(md_lines)

    return {
        "message": "Laporan berhasil dibuat.",
        "data": {
            "session_id":   session_id,
            "stats":        stats,
            "severity":     severity,
            "findings":     findings,
            "report_md":    report_md,
            "ai_analysis":  ai_analysis,
        }
    }
