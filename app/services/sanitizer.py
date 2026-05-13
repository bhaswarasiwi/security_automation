"""
Sanitizer — Strip data sensitif sebelum dikirim ke AI eksternal.

Yang di-mask:
- IP address (IPv4 & IPv6)
- Domain / subdomain / URL
- Token, API key, password, secret
- Cookie & Authorization header
- Email address
- Hash (MD5/SHA)

Data asli TIDAK dimodifikasi — sanitizer hanya membuat salinan bersih
untuk dikirim ke AI. Data lengkap tetap tersimpan di Supabase raw_output.
"""

import re
import json
import copy
from typing import Any


# ─── Pola regex ──────────────────────────────────────────────────────────────

_PATTERNS = [
    # IP address IPv4
    (re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b'), "[IP_REDACTED]"),
    # IP address IPv6
    (re.compile(r'\b(?:[0-9a-fA-F]{1,4}:){2,7}[0-9a-fA-F]{1,4}\b'), "[IPV6_REDACTED]"),
    # URL lengkap (http/https)
    (re.compile(r'https?://[^\s\'"<>{}|\\^`\[\]]+'), "[URL_REDACTED]"),
    # Domain/subdomain (anything.something.tld)
    (re.compile(r'\b(?:[a-zA-Z0-9-]+\.){2,}[a-zA-Z]{2,}\b'), "[DOMAIN_REDACTED]"),
    # Email
    (re.compile(r'\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b'), "[EMAIL_REDACTED]"),
    # Bearer token / JWT
    (re.compile(r'Bearer\s+[A-Za-z0-9\-._~+/]+=*', re.IGNORECASE), "Bearer [TOKEN_REDACTED]"),
    # JWT format (xxx.yyy.zzz)
    (re.compile(r'\beyJ[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\b'), "[JWT_REDACTED]"),
    # API key / secret patterns (key=xxx, token=xxx, secret=xxx, password=xxx)
    (re.compile(
        r'(?i)(api[_-]?key|secret|token|password|passwd|auth|authorization|cookie|session)["\s:=]+["\']?([A-Za-z0-9\-._~+/!@#$%^&*]{8,})["\']?'
    ), r'\1=[CREDENTIAL_REDACTED]'),
    # MD5 hash
    (re.compile(r'\b[a-fA-F0-9]{32}\b'), "[HASH_REDACTED]"),
    # SHA1/SHA256 hash
    (re.compile(r'\b[a-fA-F0-9]{40,64}\b'), "[HASH_REDACTED]"),
]

# Field dict yang langsung di-drop (tidak dikirim sama sekali)
_SENSITIVE_KEYS = {
    "ip", "ip_address", "host", "url", "matched-at", "matched_at",
    "curl-command", "curl_command", "request", "response",
    "raw", "raw_output", "cookie", "authorization", "set-cookie",
    "x-forwarded-for", "x-real-ip", "location", "referer",
    "email", "password", "token", "secret", "api_key",
}


# ─── Core sanitizer ──────────────────────────────────────────────────────────

def mask_text(text: str) -> str:
    """Mask semua pola sensitif dalam string."""
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def sanitize_dict(data: Any, depth: int = 0) -> Any:
    """
    Rekursif sanitasi dict/list.
    - Key sensitif → diganti placeholder
    - Value string → di-mask
    - Nested dict/list → diproses rekursif
    - Kedalaman max 6 level untuk cegah infinite loop
    """
    if depth > 6:
        return "[TRUNCATED]"

    if isinstance(data, str):
        return mask_text(data)

    if isinstance(data, dict):
        clean = {}
        for k, v in data.items():
            key_lower = str(k).lower().replace("-", "_")
            if key_lower in _SENSITIVE_KEYS:
                clean[k] = "[REDACTED]"
            else:
                clean[k] = sanitize_dict(v, depth + 1)
        return clean

    if isinstance(data, list):
        return [sanitize_dict(item, depth + 1) for item in data]

    if isinstance(data, (int, float, bool)) or data is None:
        return data

    return mask_text(str(data))


def sanitize_findings_for_ai(findings: list[dict]) -> list[dict]:
    """
    Buat salinan findings yang aman untuk dikirim ke AI.

    Yang dipertahankan (cukup untuk triage):
    - severity, status, finding (teks di-mask)
    - nama method, kategori
    - info vulnerability (tanpa URL/IP asli)

    Yang di-strip total:
    - raw_output (terlalu besar & sensitif)
    - URL asli, IP, host
    - Credential, token, cookie
    """
    safe = []
    for f in findings:
        clean = {
            "severity":   f.get("severity", "unknown"),
            "status":     f.get("status", "unknown"),
            "finding":    mask_text(str(f.get("finding", ""))),
            "created_at": f.get("created_at", ""),
        }

        # Sertakan info dari raw_output tapi hanya field aman
        raw = f.get("raw_output") or {}
        if isinstance(raw, dict):
            info = raw.get("info", {})
            if isinstance(info, dict):
                clean["vuln_name"]        = info.get("name", "")
                clean["vuln_description"] = mask_text(info.get("description", ""))
                clean["vuln_tags"]        = info.get("tags", [])
                clean["vuln_reference"]   = info.get("reference", [])  # CVE/link publik aman
                clean["vuln_severity"]    = info.get("severity", "")

        safe.append(clean)
    return safe


def sanitize_report_summary(by_severity: dict) -> dict:
    """Sanitasi ringkasan per severity untuk laporan AI."""
    clean = {}
    for sev, findings in by_severity.items():
        if isinstance(findings, list):
            clean[sev] = [mask_text(str(f)) for f in findings]
        else:
            clean[sev] = mask_text(str(findings))
    return clean