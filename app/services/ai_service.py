"""
app/services/ai_service.py (PATCHED — tambah Gemini adapter)
------------------------------------------------------------
AI provider yang di-support:
  - claude    : Anthropic Claude via anthropic SDK
  - openai    : OpenAI atau compatible endpoint (OpenRouter, Azure, etc.)
  - gemini    : Google Gemini via google-generativeai SDK  ← BARU
  - ollama    : Ollama lokal (OpenAI-compatible endpoint)

Set di .env / Render Dashboard:
  AI_PROVIDER=gemini
  GEMINI_API_KEY=AIza...
  GEMINI_MODEL=gemini-2.0-flash   (default)

Install tambahan di requirements.txt:
  google-generativeai>=0.8.0
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ─── Config ───────────────────────────────────────────────────────────────────

@dataclass
class AIConfig:
    provider:  str = "gemini"
    api_key:   str | None = None
    base_url:  str | None = None
    model:     str | None = None
    max_tokens: int = 1000

    @classmethod
    def from_env(cls) -> "AIConfig":
        provider = os.environ.get("AI_PROVIDER", "gemini").lower()

        return cls(
            provider   = provider,
            api_key    = os.environ.get(f"{provider.upper()}_API_KEY") or os.environ.get("AI_API_KEY"),
            base_url   = os.environ.get("AI_BASE_URL"),
            model      = os.environ.get("AI_MODEL"),
            max_tokens = int(os.environ.get("AI_MAX_TOKENS", "1000")),
        )


# ─── Singleton runtime config (bisa di-swap via /api/ai/switch) ──────────────

_current_config: AIConfig = AIConfig.from_env()


def get_ai_config() -> AIConfig:
    return _current_config


def set_ai_config(config: AIConfig) -> None:
    global _current_config
    _current_config = config
    logger.info("AI provider switched to: %s (model: %s)", config.provider, config.model)


# ─── Provider adapters ────────────────────────────────────────────────────────

def _call_gemini(prompt: str, config: AIConfig) -> str:
    """
    Gemini adapter via google-generativeai SDK.
    Gemini API tidak compatible dengan OpenAI format — butuh SDK sendiri.
    """
    try:
        import google.generativeai as genai
    except ImportError:
        raise RuntimeError(
            "google-generativeai belum terinstall. "
            "Tambahkan 'google-generativeai>=0.8.0' ke requirements.txt"
        )

    api_key = config.api_key or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY tidak ditemukan di environment.")

    genai.configure(api_key=api_key)

    model_name = config.model or os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
    model = genai.GenerativeModel(
        model_name       = model_name,
        generation_config = genai.types.GenerationConfig(
            max_output_tokens = config.max_tokens,
            temperature       = 0.3,   # Rendah untuk output analitik yang konsisten
        ),
    )

    response = model.generate_content(prompt)
    return response.text


def _call_claude(prompt: str, config: AIConfig) -> str:
    """Anthropic Claude adapter."""
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic belum terinstall. Tambahkan 'anthropic>=0.28.0'.")

    client = anthropic.Anthropic(api_key=config.api_key or os.environ.get("ANTHROPIC_API_KEY"))
    message = client.messages.create(
        model      = config.model or "claude-3-5-haiku-latest",
        max_tokens = config.max_tokens,
        messages   = [{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def _call_openai_compatible(prompt: str, config: AIConfig) -> str:
    """OpenAI-compatible endpoint (OpenAI, Ollama, OpenRouter, dll)."""
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("openai belum terinstall. Tambahkan 'openai>=1.0.0'.")

    client_kwargs: dict[str, Any] = {
        "api_key": config.api_key or "ollama",  # Ollama tidak butuh key valid
    }
    if config.base_url:
        client_kwargs["base_url"] = config.base_url
    elif config.provider == "ollama":
        client_kwargs["base_url"] = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")

    client = OpenAI(**client_kwargs)
    response = client.chat.completions.create(
        model      = config.model or ("llama3" if config.provider == "ollama" else "gpt-4o-mini"),
        messages   = [{"role": "user", "content": prompt}],
        max_tokens = config.max_tokens,
    )
    return response.choices[0].message.content or ""


# ─── Public interface ─────────────────────────────────────────────────────────

def call_ai(prompt: str, config: AIConfig | None = None) -> str:
    """
    Panggil AI provider sesuai konfigurasi aktif.
    Ini adalah satu-satunya function yang perlu dipanggil dari luar.

    Args:
        prompt: Prompt lengkap untuk AI
        config: Override config (default: pakai config aktif global)

    Returns:
        Teks response dari AI
    """
    cfg = config or get_ai_config()

    logger.info("Calling AI: provider=%s, model=%s", cfg.provider, cfg.model)

    dispatch = {
        "gemini":  _call_gemini,
        "claude":  _call_claude,
        "openai":  _call_openai_compatible,
        "ollama":  _call_openai_compatible,
    }

    handler = dispatch.get(cfg.provider)
    if not handler:
        raise ValueError(
            f"AI provider '{cfg.provider}' tidak didukung. "
            f"Pilihan: {list(dispatch.keys())}"
        )

    return handler(prompt, cfg)


def build_triage_prompt(findings: list[dict]) -> str:
    """
    Build prompt untuk AI triage dari list findings.
    Dipakai di report router.
    """
    findings_text = "\n".join([
        f"- [{f.get('severity', '?').upper()}] {f.get('method', '-')}: {f.get('finding', '-')}"
        for f in findings
    ])

    return f"""Kamu adalah security analyst expert. Analisis temuan vulnerability scan berikut dan berikan:

1. **Ringkasan eksekutif** (2-3 kalimat)
2. **3 temuan paling kritis** yang perlu segera diperbaiki
3. **Rekomendasi perbaikan** untuk setiap temuan kritis
4. **Risk score** keseluruhan (0-10) dengan justifikasi singkat

Gunakan bahasa Indonesia yang profesional. Format response dalam Markdown.

=== HASIL SCAN ===
{findings_text}
=================

Berikan analisis yang actionable dan to-the-point."""
