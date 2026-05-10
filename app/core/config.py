from pydantic_settings import BaseSettings
from typing import Literal

class Settings(BaseSettings):
    # ─── Supabase ───────────────────────────────────────────────────
    supabase_url: str = ""
    supabase_key: str = ""

    # ─── AI Provider (mudah diganti) ────────────────────────────────
    # Nilai: "gemini" | "claude" | "openai" | "ollama"
    ai_provider: Literal["gemini", "claude", "openai", "ollama"] = "gemini"

    # Gemini (Google AI Studio — gratis)
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    # Claude (Anthropic)
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-20250514"

    # OpenAI / OpenAI-compatible (kantor/klien)
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_base_url: str = "https://api.openai.com/v1"

    # Ollama (lokal / self-hosted)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3"

    # ─── Scanning Tools ─────────────────────────────────────────────
    subfinder_bin: str = "subfinder"
    nuclei_bin: str = "nuclei"
    httpx_bin: str = "httpx"

    # ─── Batas penggunaan AI ────────────────────────────────────────
    ai_max_tokens: int = 1000
    ai_max_findings_per_call: int = 10

    # ─── App ────────────────────────────────────────────────────────
    secret_key: str = "ganti-dengan-secret-aman"
    debug: bool = False

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
