"""
AI Service — provider bisa diganti via ENV atau endpoint /api/ai/switch
Mendukung: Gemini (Google), Claude (Anthropic), OpenAI / compatible, Ollama (lokal)

CATATAN PENGGUNAAN TOKEN:
- Gemini gratis: 1500 request/hari, 1 juta token/menit (gemini-2.0-flash)
- Jika limit habis, fallback ke analisis rule-based otomatis
- Pantau via GET /api/ai/usage
"""

import httpx
import json
from app.core.config import settings

_usage_session = {"calls": 0, "estimated_tokens": 0, "provider": settings.ai_provider}

def get_usage_stats() -> dict:
    return _usage_session.copy()

def reset_usage():
    _usage_session["calls"] = 0
    _usage_session["estimated_tokens"] = 0


async def call_ai(prompt: str, system: str = "") -> str:
    provider = settings.ai_provider
    _usage_session["calls"] += 1
    _usage_session["estimated_tokens"] += int(len(prompt.split()) * 1.3)

    try:
        if provider == "gemini":
            return await _call_gemini(prompt, system)
        elif provider == "claude":
            return await _call_claude(prompt, system)
        elif provider == "openai":
            return await _call_openai(prompt, system)
        elif provider == "ollama":
            return await _call_ollama(prompt, system)
        else:
            return _fallback_analysis(prompt)
    except Exception as e:
        return _fallback_analysis(prompt, error=str(e))


# ─── Gemini (Google AI Studio) ───────────────────────────────────────────────

async def _call_gemini(prompt: str, system: str) -> str:
    full_prompt = f"{system}\n\n{prompt}" if system else prompt
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent"
        f"?key={settings.gemini_api_key}"
    )
    body = {
        "contents": [{"parts": [{"text": full_prompt}]}],
        "generationConfig": {"maxOutputTokens": settings.ai_max_tokens},
    }
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(url, json=body)
        r.raise_for_status()
        data = r.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]


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
        return r.json()["content"][0]["text"]


# ─── OpenAI / OpenAI-compatible ──────────────────────────────────────────────

async def _call_openai(prompt: str, system: str) -> str:
    headers = {"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"}
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    body = {"model": settings.openai_model, "max_tokens": settings.ai_max_tokens, "messages": messages}
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(f"{settings.openai_base_url}/chat/completions", headers=headers, json=body)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


# ─── Ollama (lokal) ──────────────────────────────────────────────────────────

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


# ─── Fallback rule-based ──────────────────────────────────────────────────────

def _fallback_analysis(raw: str, error: str = "") -> str:
    note = f"[FALLBACK — AI tidak tersedia: {error}]\n" if error else "[FALLBACK — mode analisis lokal]\n"
    severity = "info"
    findings = []
    raw_lower = raw.lower()

    for kw in ["rce", "remote code", "sql injection", "sqli", "authentication bypass"]:
        if kw in raw_lower:
            severity = "critical"
            findings.append(f"Terdeteksi pola kritis: {kw}")
    for kw in ["xss", "ssrf", "idor", "broken auth", "open redirect"]:
        if kw in raw_lower and severity != "critical":
            severity = "high"
            findings.append(f"Terdeteksi pola tinggi: {kw}")
    for kw in ["csrf", "information disclosure", "misconfiguration"]:
        if kw in raw_lower and severity not in ["critical", "high"]:
            severity = "medium"
            findings.append(f"Terdeteksi pola menengah: {kw}")

    summary = "\n".join(findings) if findings else "Tidak ada pola vulnerability yang ditemukan."
    return f"{note}Severity: {severity}\n{summary}"


# ─── Triage findings ─────────────────────────────────────────────────────────

async def triage_findings(findings: list[dict]) -> dict:
    limited = findings[:settings.ai_max_findings_per_call]
    system = (
        "Kamu adalah security analyst yang menganalisis hasil bug bounty. "
        "Berikan triage singkat: severity, confidence, rekomendasi langkah berikutnya. "
        "Jawab dalam format JSON: {severity, confidence, summary, next_steps}."
    )
    prompt = f"Analisis temuan berikut:\n{json.dumps(limited, indent=2)}"
    raw = await call_ai(prompt, system)
    try:
        clean = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        return json.loads(clean)
    except Exception:
        return {"summary": raw, "severity": "unknown", "confidence": "low", "next_steps": []}
