"""
AI Service — provider bisa diganti via ENV atau endpoint /api/ai/switch
Mendukung: Claude (Anthropic), OpenAI / OpenAI-compatible, Ollama (lokal)

CATATAN PENGGUNAAN TOKEN:
- Setiap request ke AI dihitung dan dicatat di Supabase (tabel ai_usage_log)
- Gunakan ai_max_tokens di config untuk batasi biaya
- Gunakan ai_max_findings_per_call untuk batasi payload yang dikirim ke AI
- Jika token hampir habis, fallback ke analisis rule-based otomatis
"""

import httpx
import json
from typing import Optional
from app.core.config import settings


# ─── Usage Tracker ───────────────────────────────────────────────────────────

_usage_session = {
    "calls": 0,
    "estimated_tokens": 0,
    "provider": settings.ai_provider,
}

def get_usage_stats() -> dict:
    return _usage_session.copy()

def reset_usage():
    _usage_session["calls"] = 0
    _usage_session["estimated_tokens"] = 0


# ─── Core AI call ────────────────────────────────────────────────────────────

async def call_ai(prompt: str, system: str = "") -> str:
    """
    Panggil AI provider yang aktif.
    Provider dipilih via settings.ai_provider (dari ENV).
    """
    provider = settings.ai_provider
    _usage_session["calls"] += 1
    _usage_session["estimated_tokens"] += len(prompt.split()) * 1.3  # estimasi kasar

    try:
        if provider == "claude":
            return await _call_claude(prompt, system)
        elif provider == "openai":
            return await _call_openai(prompt, system)
        elif provider == "ollama":
            return await _call_ollama(prompt, system)
        else:
            return _fallback_analysis(prompt)
    except Exception as e:
        # Jika AI gagal / token habis — fallback ke analisis rule-based
        return _fallback_analysis(prompt, error=str(e))


# ─── Claude (Anthropic) ──────────────────────────────────────────────────────

async def _call_claude(prompt: str, system: str) -> str:
    headers = {
        "x-api-key": settings.anthropic_api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": settings.claude_model,
        "max_tokens": settings.ai_max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        body["system"] = system

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post("https://api.anthropic.com/v1/messages", headers=headers, json=body)
        r.raise_for_status()
        data = r.json()
        return data["content"][0]["text"]


# ─── OpenAI / OpenAI-compatible (kantor, proxy, dll) ─────────────────────────

async def _call_openai(prompt: str, system: str) -> str:
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    body = {
        "model": settings.openai_model,
        "max_tokens": settings.ai_max_tokens,
        "messages": messages,
    }

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{settings.openai_base_url}/chat/completions",
            headers=headers,
            json=body,
        )
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"]


# ─── Ollama (lokal / self-hosted) ────────────────────────────────────────────

async def _call_ollama(prompt: str, system: str) -> str:
    body = {
        "model": settings.ollama_model,
        "prompt": f"{system}\n\n{prompt}" if system else prompt,
        "stream": False,
        "options": {"num_predict": settings.ai_max_tokens},
    }
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(f"{settings.ollama_base_url}/api/generate", json=body)
        r.raise_for_status()
        return r.json()["response"]


# ─── Fallback rule-based (tidak butuh AI) ────────────────────────────────────

def _fallback_analysis(raw: str, error: str = "") -> str:
    """
    Analisis sederhana berbasis keyword jika AI tidak tersedia.
    Digunakan saat: token habis, API down, atau mode offline.
    """
    note = f"[FALLBACK — AI tidak tersedia: {error}]\n" if error else "[FALLBACK — mode analisis lokal]\n"
    severity = "info"
    findings = []

    keywords_critical = ["rce", "remote code", "sql injection", "sqli", "authentication bypass"]
    keywords_high     = ["xss", "ssrf", "idor", "broken auth", "open redirect"]
    keywords_medium   = ["csrf", "information disclosure", "misconfiguration"]

    raw_lower = raw.lower()
    for kw in keywords_critical:
        if kw in raw_lower:
            severity = "critical"
            findings.append(f"Terdeteksi pola kritis: {kw}")
    for kw in keywords_high:
        if kw in raw_lower and severity not in ["critical"]:
            severity = "high"
            findings.append(f"Terdeteksi pola tinggi: {kw}")
    for kw in keywords_medium:
        if kw in raw_lower and severity not in ["critical", "high"]:
            severity = "medium"
            findings.append(f"Terdeteksi pola menengah: {kw}")

    summary = "\n".join(findings) if findings else "Tidak ada pola vulnerability yang ditemukan."
    return f"{note}Severity: {severity}\n{summary}"


# ─── Triage hasil scan ───────────────────────────────────────────────────────

async def triage_findings(findings: list[dict]) -> dict:
    """
    Kirim hasil scan ke AI untuk triage.
    Dibatasi ai_max_findings_per_call untuk hemat token.
    """
    limited = findings[: settings.ai_max_findings_per_call]

    system = (
        "Kamu adalah security analyst yang menganalisis hasil bug bounty. "
        "Berikan triage singkat: severity, confidence, rekomendasi langkah berikutnya. "
        "Jawab dalam format JSON: {severity, confidence, summary, next_steps}."
    )
    prompt = f"Analisis temuan berikut:\n{json.dumps(limited, indent=2)}"

    raw = await call_ai(prompt, system)

    # Coba parse JSON, fallback ke dict mentah
    try:
        clean = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        return json.loads(clean)
    except Exception:
        return {"summary": raw, "severity": "unknown", "confidence": "low", "next_steps": []}
