"""
Scanning Service
Menjalankan: subfinder (subdomain enum), nuclei (vuln scan), httpx (probe)
Output disimpan ke Supabase: scan_session + test_result
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone
from app.core.config import settings
from app.core.supabase import get_supabase


async def _run_cmd(cmd: list[str], timeout: int = 300) -> tuple[str, str, int]:
    """Jalankan command, return (stdout, stderr, returncode)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return stdout.decode(), stderr.decode(), proc.returncode
    except asyncio.TimeoutError:
        return "", "Timeout exceeded", 1
    except FileNotFoundError:
        return "", f"Binary tidak ditemukan: {cmd[0]}", 1


# ─── Subfinder ───────────────────────────────────────────────────────────────

async def run_subfinder(domain: str) -> list[str]:
    """Enumerate subdomain via subfinder. Return list subdomain."""
    cmd = [settings.subfinder_bin, "-d", domain, "-silent", "-json"]
    stdout, stderr, code = await _run_cmd(cmd, timeout=120)

    subdomains = []
    for line in stdout.strip().splitlines():
        try:
            obj = json.loads(line)
            subdomains.append(obj.get("host", ""))
        except Exception:
            if line.strip():
                subdomains.append(line.strip())

    return [s for s in subdomains if s]


# ─── httpx probe ─────────────────────────────────────────────────────────────

async def run_httpx(targets: list[str]) -> list[dict]:
    """Probe list target, return detail status/title/tech."""
    if not targets:
        return []

    # Tulis targets ke stdin
    input_data = "\n".join(targets).encode()
    cmd = [
        settings.httpx_bin,
        "-silent", "-json",
        "-status-code", "-title", "-tech-detect", "-follow-redirects",
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(input=input_data), timeout=120)
    except (asyncio.TimeoutError, FileNotFoundError):
        return []

    results = []
    for line in stdout.decode().strip().splitlines():
        try:
            results.append(json.loads(line))
        except Exception:
            pass
    return results


# ─── Nuclei ──────────────────────────────────────────────────────────────────

async def run_nuclei(targets: list[str], severity: str = "medium,high,critical") -> list[dict]:
    """Run nuclei scan. Severity: info,low,medium,high,critical."""
    if not targets:
        return []

    input_data = "\n".join(targets).encode()
    cmd = [
        settings.nuclei_bin,
        "-json", "-silent",
        "-severity", severity,
        "-rate-limit", "10",       # batasi request/detik (etis)
        "-timeout", "10",
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(input=input_data), timeout=300)
    except (asyncio.TimeoutError, FileNotFoundError):
        return []

    results = []
    for line in stdout.decode().strip().splitlines():
        try:
            results.append(json.loads(line))
        except Exception:
            pass
    return results


# ─── Full scan pipeline ───────────────────────────────────────────────────────

async def run_full_scan(session_id: str, target_id: str, base_url: str, method_id: str):
    """
    Pipeline lengkap: subfinder → httpx → nuclei → simpan ke Supabase.
    Dipanggil sebagai background task.
    """
    db = get_supabase()
    now = datetime.now(timezone.utc).isoformat()

    # Update status session → running
    db.table("scan_session").update({
        "status": "running",
        "started_at": now,
    }).eq("id", session_id).execute()

    try:
        # Ekstrak domain dari base_url
        from urllib.parse import urlparse
        domain = urlparse(base_url).netloc or base_url

        # 1. Subfinder
        subdomains = await run_subfinder(domain)
        all_targets = list({base_url, *[f"https://{s}" for s in subdomains]})

        _save_result(db, session_id, method_id, "pass", "info",
                     f"Subfinder menemukan {len(subdomains)} subdomain",
                     {"subdomains": subdomains})

        # 2. httpx probe
        probed = await run_httpx(all_targets)
        live_targets = [p["url"] for p in probed if "url" in p]

        _save_result(db, session_id, method_id, "pass", "info",
                     f"httpx menemukan {len(live_targets)} host aktif",
                     {"probed": probed})

        # 3. Nuclei
        nuclei_findings = await run_nuclei(live_targets)

        for finding in nuclei_findings:
            severity = finding.get("info", {}).get("severity", "info")
            name     = finding.get("info", {}).get("name", "Unknown")
            matched  = finding.get("matched-at", "")
            _save_result(db, session_id, method_id,
                         "fail" if severity in ["high", "critical"] else "pass",
                         severity, f"{name} — {matched}", finding)

        # Update session selesai
        db.table("scan_session").update({
            "status": "completed",
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "notes": f"Selesai: {len(nuclei_findings)} temuan dari {len(live_targets)} host",
        }).eq("id", session_id).execute()

    except Exception as e:
        db.table("scan_session").update({
            "status": "failed",
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "notes": str(e),
        }).eq("id", session_id).execute()


def _save_result(db, session_id, method_id, status, severity, finding, raw_output):
    db.table("test_result").insert({
        "id": str(uuid.uuid4()),
        "session_id": session_id,
        "method_id": method_id,
        "status": status,
        "severity": severity,
        "finding": finding,
        "raw_output": raw_output,
    }).execute()
