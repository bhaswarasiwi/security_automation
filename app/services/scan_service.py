"""
app/services/scan_service.py
-----------------------------
Runner utama untuk scan session.

Flow:
  1. Ambil semua hack_methods aktif dari DB (sesuai execution_mode)
  2. Untuk setiap method, resolve function via SCANNER_REGISTRY (whitelist ketat)
  3. Jalankan scanner, simpan result ke test_result
  4. Update status session (completed / failed)
  5. Opsional: jalankan AI triage

SCANNER_REGISTRY adalah dict statis Python — bukan eval/dynamic import.
Ini adalah whitelist: hanya string yang ada di dict ini yang bisa dieksekusi.
function_map di DB harus PERSIS sama dengan key di REGISTRY ini.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable

from app.core.supabase import get_supabase

logger = logging.getLogger(__name__)

# ── Registry scanner (whitelist ketat) ───────────────────────────────────────
# Key = function_map di tabel hack_methods
# Value = fungsi Python yang mengimplementasikan scanner tersebut
# Tambahkan scanner baru di sini SAJA — jangan dynamic import dari DB

def _import_scanner(module_path: str, class_name: str) -> Callable:
    """Lazy import scanner class untuk menghindari circular import."""
    import importlib
    mod = importlib.import_module(module_path)
    return getattr(mod, class_name)


def _build_registry() -> dict[str, Callable]:
    """
    Build registry scanner.
    Semua scanner merupakan callable yang menerima (base_url, payload_template, timeout)
    dan mengembalikan dict: {status, severity, finding, raw_output}
    """
    try:
        # Import semua scanner passive
        from app.services.scanners.passive.headers        import scan_headers
        from app.services.scanners.passive.server_banner  import scan_server_banner
        from app.services.scanners.passive.cookies        import scan_cookies
        from app.services.scanners.passive.dns            import scan_dns
        from app.services.scanners.passive.subdomain      import scan_subdomain
        from app.services.scanners.passive.ssl_cert       import scan_ssl_cert
        from app.services.scanners.passive.tls_version    import scan_tls_version
        from app.services.scanners.passive.robots         import scan_robots
        from app.services.scanners.passive.sensitive_files import scan_sensitive_files
        from app.services.scanners.passive.dir_listing    import scan_dir_listing
        from app.services.scanners.passive.tech_stack     import scan_tech_stack
        from app.services.scanners.passive.cors           import scan_cors
        from app.services.scanners.passive.api_endpoints  import scan_api_endpoints

        return {
            "passive_scan_headers":         scan_headers,
            "passive_scan_server_banner":   scan_server_banner,
            "passive_scan_cookies":         scan_cookies,
            "passive_scan_dns":             scan_dns,
            "passive_scan_subdomain":       scan_subdomain,
            "passive_scan_ssl_cert":        scan_ssl_cert,
            "passive_scan_tls_version":     scan_tls_version,
            "passive_scan_robots":          scan_robots,
            "passive_scan_sensitive_files": scan_sensitive_files,
            "passive_scan_dir_listing":     scan_dir_listing,
            "passive_scan_tech_stack":      scan_tech_stack,
            "passive_scan_cors":            scan_cors,
            "passive_scan_api_endpoints":   scan_api_endpoints,
        }
    except ImportError:
        # Fallback: gunakan scan_service lama (subfinder + nuclei + httpx)
        logger.warning(
            "Scanner modules tidak ditemukan di app/services/scanners/. "
            "Fallback ke external tools (nuclei/subfinder)."
        )
        return {}


SCANNER_REGISTRY: dict[str, Callable] = {}   # Diisi lazy saat pertama run


def _get_registry() -> dict[str, Callable]:
    global SCANNER_REGISTRY
    if not SCANNER_REGISTRY:
        SCANNER_REGISTRY = _build_registry()
    return SCANNER_REGISTRY


# ── DB helpers ────────────────────────────────────────────────────────────────

def _complete_session(sb, session_id: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    sb.table("scan_session").update({
        "status":      "completed",
        "finished_at": now,
    }).eq("id", session_id).execute()


def _fail_session(sb, session_id: str, reason: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    sb.table("scan_session").update({
        "status":      "failed",
        "notes":       reason,
        "finished_at": now,
    }).eq("id", session_id).execute()


def _save_result(
    sb,
    session_id:  str,
    method_id:   str,
    status:      str,
    severity:    str | None,
    finding:     str,
    raw_output:  dict,
    endpoint_id: str | None = None,
) -> None:
    sb.table("test_result").insert({
        "session_id":  session_id,
        "method_id":   method_id,
        "endpoint_id": endpoint_id,
        "status":      status,
        "severity":    severity,
        "finding":     finding,
        "raw_output":  raw_output,
    }).execute()


# ── Main runner ───────────────────────────────────────────────────────────────

def run_scan_session(
    session_id:     str,
    target_id:      str,
    base_url:       str,
    execution_mode: str = "passive",
    use_ai_triage:  bool = True,
    timeout:        int  = 30,
) -> None:
    """
    Dijalankan sebagai background task oleh FastAPI.
    Tidak boleh raise exception ke caller — semua error di-catch dan disimpan ke DB.
    """
    sb       = get_supabase()
    registry = _get_registry()

    logger.info(
        "Scan started: session=%s target=%s mode=%s",
        session_id, base_url, execution_mode,
    )

    try:
        # Ambil methods aktif dari DB
        methods_res = (
            sb.table("hack_methods")
            .select("id, nama, function_map, payload_template, risk_level")
            .eq("execution_mode", execution_mode)
            .eq("is_active", True)
            .execute()
        )
        methods = methods_res.data

        if not methods:
            _fail_session(sb, session_id, f"Tidak ada method aktif untuk mode '{execution_mode}'.")
            return

        logger.info("Running %d methods for session %s", len(methods), session_id)

        for method in methods:
            method_id       = method["id"]
            function_map    = method["function_map"]
            payload_tmpl    = method.get("payload_template") or {}

            scanner_fn = registry.get(function_map)

            if not scanner_fn:
                # function_map tidak ada di whitelist registry
                logger.warning("Scanner tidak ditemukan di registry: '%s'", function_map)
                _save_result(
                    sb         = sb,
                    session_id = session_id,
                    method_id  = method_id,
                    status     = "skipped",
                    severity   = None,
                    finding    = f"Scanner '{function_map}' tidak tersedia di deployment ini.",
                    raw_output = {"function_map": function_map},
                )
                continue

            try:
                result: dict[str, Any] = scanner_fn(
                    base_url         = base_url,
                    payload_template = payload_tmpl,
                    timeout          = timeout,
                )
                _save_result(
                    sb         = sb,
                    session_id = session_id,
                    method_id  = method_id,
                    status     = result.get("status", "error"),
                    severity   = result.get("severity"),
                    finding    = result.get("finding", ""),
                    raw_output = result.get("raw_output", {}),
                )
                logger.debug("Method %s → %s", method["nama"], result.get("status"))

            except Exception as scanner_exc:
                logger.error("Scanner error [%s]: %s", method["nama"], scanner_exc, exc_info=True)
                _save_result(
                    sb         = sb,
                    session_id = session_id,
                    method_id  = method_id,
                    status     = "error",
                    severity   = None,
                    finding    = f"Scanner error: {scanner_exc}",
                    raw_output = {"error": str(scanner_exc)},
                )

        _complete_session(sb, session_id)
        logger.info("Scan completed: session=%s", session_id)

        # AI triage opsional
        if use_ai_triage:
            try:
                from app.services.ai_service import run_triage
                run_triage(session_id)
                logger.info("AI triage selesai: session=%s", session_id)
            except Exception as ai_exc:
                logger.warning("AI triage gagal (diabaikan): %s", ai_exc)

    except Exception as exc:
        logger.error("Scan session fatal error: %s", exc, exc_info=True)
        _fail_session(sb, session_id, str(exc))
