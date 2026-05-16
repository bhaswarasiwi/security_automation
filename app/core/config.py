"""
app/core/config.py
------------------
Semua konfigurasi dibaca dari environment variables.
Gunakan pydantic-settings agar ada validasi tipe dan default yang jelas.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Supabase ──────────────────────────────────────────────────────────
    supabase_url: str
    supabase_key: str                      # service_role key (backend only)

    # ── CORS & deployment ─────────────────────────────────────────────────
    # Pisahkan domain dengan koma di env:
    # ALLOWED_ORIGINS=https://app.vercel.app,http://localhost:3000
    allowed_origins: str = "http://localhost:3000"
    environment: str = "development"       # "production" → lock /docs

    # ── AI provider ───────────────────────────────────────────────────────
    ai_provider: str = "gemini"            # gemini | claude | openai | ollama
    ai_model: str | None = None
    ai_max_tokens: int = 1000
    ai_max_findings_per_call: int = 10

    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.0-flash"

    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    ollama_base_url: str = "http://localhost:11434/v1"

    # ── Security ──────────────────────────────────────────────────────────
    secret_key: str = "change-me-in-production"

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
