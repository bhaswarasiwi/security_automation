"""
app/agent/repository.py (PATCHED — multi-tenant)
-------------------------------------------------
Perubahan dari versi lama:
- create_target() dan create_session() menerima user_id
- get_target() dan get_session() bisa filter by user_id
  (jika user_id=None → backend/admin mode, skip filter)
- Semua method lain tidak berubah
"""

from __future__ import annotations

import logging
from typing import Any

from app.db.client import get_supabase

logger = logging.getLogger(__name__)


class ScanRepository:
    """Repository untuk semua operasi DB yang dibutuhkan agent."""

    def __init__(self) -> None:
        self.sb = get_supabase()

    # ------------------------------------------------------------------
    # hack_methods
    # ------------------------------------------------------------------

    def get_active_methods(self, execution_mode: str = "passive") -> list[dict]:
        """Ambil semua method aktif berdasarkan execution_mode."""
        result = (
            self.sb.table("hack_methods")
            .select("id, nama, function_map, payload_template, risk_level, domain_kategori")
            .eq("execution_mode", execution_mode)
            .eq("is_active", True)
            .execute()
        )
        logger.info("Loaded %d methods (mode: %s)", len(result.data), execution_mode)
        return result.data

    # ------------------------------------------------------------------
    # target
    # ------------------------------------------------------------------

    def get_target(self, target_id: str, user_id: str | None = None) -> dict | None:
        """
        Ambil satu target berdasarkan ID.

        Args:
            target_id: UUID target
            user_id: Jika diisi, filter hanya milik user ini (untuk endpoint user-facing).
                     Jika None, skip filter user (untuk operasi internal agent).
        """
        query = (
            self.sb.table("target")
            .select("*")
            .eq("id", target_id)
            .eq("is_active", True)
        )
        if user_id:
            query = query.eq("user_id", user_id)

        result = query.single().execute()
        return result.data

    def get_target_endpoints(self, target_id: str) -> list[dict]:
        """Ambil semua endpoint aktif dari sebuah target."""
        result = (
            self.sb.table("target_endpoint")
            .select("id, path, method")
            .eq("target_id", target_id)
            .eq("is_active", True)
            .execute()
        )
        return result.data

    def create_target(
        self,
        nama:      str,
        jenis:     str,
        base_url:  str,
        deskripsi: str = "",
        user_id:   str | None = None,  # ← BARU
    ) -> dict:
        """Buat target baru dan kembalikan data yang tersimpan."""
        payload = {
            "nama":      nama,
            "jenis":     jenis,
            "base_url":  base_url,
            "deskripsi": deskripsi,
        }
        if user_id:
            payload["user_id"] = user_id

        result = (
            self.sb.table("target")
            .insert(payload)
            .execute()
        )
        return result.data[0]

    # ------------------------------------------------------------------
    # scan_session
    # ------------------------------------------------------------------

    def create_session(
        self,
        target_id: str,
        user_id:   str | None = None,  # ← BARU
        nama:      str | None = None,
    ) -> dict:
        """Buat scan session baru dengan status 'running'."""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")

        payload: dict[str, Any] = {
            "target_id":  target_id,
            "status":     "running",
            "started_at": now,
        }
        if nama:
            payload["nama"] = nama
        if user_id:
            payload["user_id"] = user_id

        result = (
            self.sb.table("scan_session")
            .insert(payload)
            .execute()
        )
        session = result.data[0]
        logger.info("Session created: %s", session["id"])
        return session

    def complete_session(self, session_id: str) -> None:
        """Tandai session sebagai completed."""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        self.sb.table("scan_session").update({
            "status":      "completed",
            "finished_at": now,
        }).eq("id", session_id).execute()
        logger.info("Session completed: %s", session_id)

    def fail_session(self, session_id: str, reason: str) -> None:
        """Tandai session sebagai failed."""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        self.sb.table("scan_session").update({
            "status":      "failed",
            "notes":       reason,
            "finished_at": now,
        }).eq("id", session_id).execute()
        logger.warning("Session failed: %s — %s", session_id, reason)

    def get_session(self, session_id: str, user_id: str | None = None) -> dict | None:
        """
        Ambil satu session beserta relasinya.

        Args:
            session_id: UUID session
            user_id: Jika diisi, pastikan session milik user ini.
        """
        query = (
            self.sb.table("scan_session")
            .select("*, target(*)")
            .eq("id", session_id)
        )
        if user_id:
            query = query.eq("user_id", user_id)

        result = query.single().execute()
        return result.data

    def list_sessions(
        self,
        user_id:   str | None = None,
        target_id: str | None = None,
        limit:     int = 20,
    ) -> list[dict]:
        """Daftar session terbaru. Filter by user_id untuk multi-tenant."""
        query = (
            self.sb.table("scan_session")
            .select("id, nama, status, started_at, finished_at, target(nama, base_url)")
            .order("created_at", desc=True)
            .limit(limit)
        )
        if user_id:
            query = query.eq("user_id", user_id)
        if target_id:
            query = query.eq("target_id", target_id)
        return query.execute().data

    # ------------------------------------------------------------------
    # test_result (tidak berubah — isolasi via scan_session.user_id)
    # ------------------------------------------------------------------

    def save_result(
        self,
        session_id:  str,
        method_id:   str,
        status:      str,
        severity:    str | None,
        finding:     str,
        raw_output:  dict,
        endpoint_id: str | None = None,
    ) -> dict:
        result = (
            self.sb.table("test_result")
            .insert({
                "session_id":  session_id,
                "method_id":   method_id,
                "endpoint_id": endpoint_id,
                "status":      status,
                "severity":    severity,
                "finding":     finding,
                "raw_output":  raw_output,
            })
            .execute()
        )
        return result.data[0]

    def get_results_by_session(self, session_id: str) -> list[dict]:
        result = (
            self.sb.table("test_result")
            .select("*, hack_methods(nama, domain_kategori, risk_level), target_endpoint(path, method)")
            .eq("session_id", session_id)
            .order("created_at")
            .execute()
        )
        return result.data

    def get_summary_by_session(self, session_id: str) -> dict[str, Any]:
        results = self.get_results_by_session(session_id)

        summary: dict[str, Any] = {
            "total":   len(results),
            "pass":    0,
            "fail":    0,
            "error":   0,
            "skipped": 0,
            "by_severity": {
                "critical": 0,
                "high":     0,
                "medium":   0,
                "low":      0,
                "info":     0,
            },
            "findings": [],
        }

        for r in results:
            summary[r["status"]] = summary.get(r["status"], 0) + 1
            if r["status"] == "fail" and r.get("severity"):
                summary["by_severity"][r["severity"]] = \
                    summary["by_severity"].get(r["severity"], 0) + 1
                summary["findings"].append({
                    "method":   r.get("hack_methods", {}).get("nama", "-"),
                    "severity": r["severity"],
                    "finding":  r["finding"],
                })

        return summary
