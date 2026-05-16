"""
app/services/ai_service.py
--------------------------
AI provider layer. Support: Gemini, Claude, OpenAI, Ollama.
Provider aktif bisa diganti runtime via /api/ai/switch (admin only).

Setup Gemini di .env / Render:
  AI_PROVIDER=gemini
  GEMINI_API_KEY=AIza...
  GEMINI_MODEL=gemini-2.0-flash

Install: tambahkan ke requirements.txt:
  google-generativeai>=0.8.0
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# ── Usage tracking ────────────────────────────────────────────────────────────
_usage: dict[str, int] = {"calls": 0, "estimated_tokens_in": 0, "estimated_tokens_out": 0}


def get_usage_stats() -> dict:
    return dict(_usage)


def reset_usage_stats() -> None:
    _usage["calls"] = 0
    _usage["estimated_tokens_in"]  = 0
    _usage["estimated_tokens_out"] = 0


# ── Config ────────────────────────────────────────────────────────────────────

@dataclass
class AIConfig:
    provider:   str        = "gemini"
    api_key:    str | None = None
    base_url:   str | None = None
    model:      str | None = None
    max_tokens: int        = 1000

    @classmethod
    def from_settings(cls) -> "AIConfig":
        s = get_settings()
        return cls(
            provider   = s.ai_provider,
            api_key    = (
                s.gemini_api_key      if s.ai_provider == "gemini"  else
                s.anthropic_api_key   if s.ai_provider == "claude"  else
                s.openai_api_key
            ),
            base_url   = s.openai_base_url,
            model      = s.ai_model,
            max_tokens = s.ai_max_tokens,
        )


# Singleton runtime config
_current_config: AIConfig = AIConfig.from_settings()


def get_ai_config() -> AIConfig:
    return _current_config


def set_ai_config(config: AIConfig) -> None:
    global _current_config
    _current_config = config
    logger.info("AI provider switched → %s (model: %s)", config.provider, config.model)


# ── Provider adapters ─────────────────────────────────────────────────────────

def _call_gemini(prompt: str, cfg: AIConfig) -> str:
    try:
        import google.generativeai as genai
    except ImportError:
        raise RuntimeError(
            "google-generativeai belum terinstall. "
            "Tambahkan 'google-generativeai>=0.8.0' ke requirements.txt"
        )
    s       = get_settings()
    api_key = cfg.api_key or s.gemini_api_key
    if not api_key:
        raise ValueError("GEMINI_API_KEY tidak ditemukan.")

    genai.configure(api_key=api_key)
    model_name = cfg.model or s.gemini_model
    model      = genai.GenerativeModel(
        model_name        = model_name,
        generation_config = genai.types.GenerationConfig(
            max_output_tokens = cfg.max_tokens,
            temperature       = 0.3,
        ),
    )
    resp = model.generate_content(prompt)
    return resp.text


def _call_claude(prompt: str, cfg: AIConfig) -> str:
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic belum terinstall. Tambahkan 'anthropic>=0.28.0'.")

    s      = get_settings()
    client = anthropic.Anthropic(api_key=cfg.api_key or s.anthropic_api_key)
    msg    = client.messages.create(
        model      = cfg.model or "claude-3-5-haiku-latest",
        max_tokens = cfg.max_tokens,
        messages   = [{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


def _call_openai_compatible(prompt: str, cfg: AIConfig) -> str:
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("openai belum terinstall. Tambahkan 'openai>=1.0.0'.")

    s              = get_settings()
    client_kwargs: dict[str, Any] = {
        "api_key": cfg.api_key or "ollama",
    }
    if cfg.base_url:
        client_kwargs["base_url"] = cfg.base_url
    elif cfg.provider == "ollama":
        client_kwargs["base_url"] = s.ollama_base_url

    client = OpenAI(**client_kwargs)
    resp   = client.chat.completions.create(
        model      = cfg.model or ("llama3" if cfg.provider == "ollama" else "gpt-4o-mini"),
        messages   = [{"role": "user", "content": prompt}],
        max_tokens = cfg.max_tokens,
    )
    return resp.choices[0].message.content or ""


_DISPATCH = {
    "gemini": _call_gemini,
    "claude": _call_claude,
    "openai": _call_openai_compatible,
    "ollama": _call_openai_compatible,
}


def call_ai(prompt: str, config: AIConfig | None = None) -> str:
    """Panggil AI provider aktif. Satu-satunya fungsi yang perlu dipanggil dari luar."""
    cfg     = config or get_ai_config()
    handler = _DISPATCH.get(cfg.provider)
    if not handler:
        raise ValueError(f"Provider '{cfg.provider}' tidak didukung. Pilihan: {list(_DISPATCH)}")

    logger.info("Calling AI: provider=%s model=%s", cfg.provider, cfg.model)

    result = handler(prompt, cfg)

    # Update usage stats (estimasi kasar)
    _usage["calls"] += 1
    _usage["estimated_tokens_in"]  += len(prompt) // 4
    _usage["estimated_tokens_out"] += len(result) // 4

    return result


def test_ai_connection(prompt: str = "Halo.") -> str:
    return call_ai(prompt)


# ── Triage ────────────────────────────────────────────────────────────────────

def _build_triage_prompt(findings: list[dict]) -> str:
    s = get_settings()
    findings = findings[: s.ai_max_findings_per_call]
    lines    = "\n".join(
        f"- [{f.get('severity','?').upper()}] {f.get('method','-')}: {f.get('finding','-')}"
        for f in findings
    )
    return f"""Kamu adalah security analyst expert. Analisis temuan berikut:

{lines}

Berikan dalam Bahasa Indonesia:
1. **Ringkasan eksekutif** (2-3 kalimat)
2. **3 temuan paling kritis** yang perlu segera diperbaiki
3. **Rekomendasi perbaikan** untuk masing-masing
4. **Risk score keseluruhan** (0-10) dengan justifikasi

Format: Markdown. Gaya: profesional dan actionable."""


def run_triage(session_id: str) -> str:
    """Jalankan AI triage untuk satu session. Return teks analisis Markdown."""
    from app.core.supabase import get_supabase
    sb = get_supabase()

    rows = (
        sb.table("test_result")
        .select("severity, finding, hack_methods(nama)")
        .eq("session_id", session_id)
        .eq("status", "fail")
        .execute()
    ).data

    if not rows:
        return "_Tidak ada vulnerability yang ditemukan untuk dianalisis._"

    findings = [
        {
            "method":   (r.get("hack_methods") or {}).get("nama", "-"),
            "severity": r.get("severity", "info"),
            "finding":  r.get("finding", "-"),
        }
        for r in rows
    ]
    prompt = _build_triage_prompt(findings)
    return call_ai(prompt)
