from pydantic_settings import BaseSettings
from typing import Literal
import os

class Settings(BaseSettings):
    # ─── Supabase ───────────────────────────────────────────────────
    supabase_url: str = ""
    supabase_key: str = ""  # service_role key (bukan anon key)

    # ─── AI Provider (mudah diganti) ────────────────────────────────
    # Nilai: "claude" | "openai" | "ollama"
    ai_provider: Literal["claude", "openai", "ollama"] = "claude"

    # Claude (Anthropic)
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-20250514"

    # OpenAI / OpenAI-compatible (kantor/klien)
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_base_url: str = "https://api.openai.com/v1"  # bisa ganti ke proxy kantor

    # Ollama (lokal / self-hosted)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3"

    # ─── Scanning Tools ─────────────────────────────────────────────
    # Lokasi binary (Render install via script; lokal via PATH)
    subfinder_bin: str = "subfinder"
    nuclei_bin: str = "nuclei"
    httpx_bin: str = "httpx"

    # ─── Batas penggunaan AI (jaga-jaga token) ──────────────────────
    ai_max_tokens: int = 1000          # max token per request ke AI
    ai_max_findings_per_call: int = 10  # batasi temuan yang dikirim ke AI sekaligus

    # ─── App ────────────────────────────────────────────────────────
    secret_key: str = "ganti-dengan-secret-aman"
    debug: bool = False

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
