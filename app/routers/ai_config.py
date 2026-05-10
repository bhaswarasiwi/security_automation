"""
AI Config Router
Endpoint untuk ganti provider AI tanpa restart server.
Berguna saat pindah dari akun pribadi ke akun kantor / klien.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Literal, Optional
from app.core.config import settings
from app.services.ai_service import get_usage_stats, reset_usage, call_ai

router = APIRouter()


class SwitchProviderRequest(BaseModel):
    provider: Literal["claude", "openai", "ollama"]

    # Override optional — jika tidak diisi, pakai dari config / ENV
    api_key: Optional[str] = None
    model: Optional[str] = None
    base_url: Optional[str] = None  # untuk openai-compatible / proxy kantor


@router.get("/provider")
def get_current_provider():
    """Cek provider AI yang sedang aktif + config saat ini."""
    return {
        "provider": settings.ai_provider,
        "claude_model": settings.claude_model,
        "openai_model": settings.openai_model,
        "openai_base_url": settings.openai_base_url,
        "ollama_model": settings.ollama_model,
        "ollama_base_url": settings.ollama_base_url,
        "ai_max_tokens": settings.ai_max_tokens,
        "ai_max_findings_per_call": settings.ai_max_findings_per_call,
    }


@router.post("/switch")
def switch_provider(body: SwitchProviderRequest):
    """
    Ganti AI provider secara runtime (tanpa restart).
    
    Contoh use case:
    - Pindah dari Claude (pribadi) ke OpenAI (kantor)
    - Pindah ke Ollama saat offline / hemat token
    - Pindah ke proxy kantor: base_url = 'https://ai.kantor.com/v1'
    """
    settings.ai_provider = body.provider

    if body.provider == "claude" and body.api_key:
        settings.anthropic_api_key = body.api_key
    if body.provider == "claude" and body.model:
        settings.claude_model = body.model

    if body.provider == "openai":
        if body.api_key:
            settings.openai_api_key = body.api_key
        if body.model:
            settings.openai_model = body.model
        if body.base_url:
            settings.openai_base_url = body.base_url  # proxy kantor / klien

    if body.provider == "ollama":
        if body.base_url:
            settings.ollama_base_url = body.base_url
        if body.model:
            settings.ollama_model = body.model

    return {
        "message": f"Provider berhasil diganti ke: {body.provider}",
        "provider": settings.ai_provider,
    }


@router.get("/usage")
def ai_usage():
    """
    Cek estimasi penggunaan AI sesi ini.
    Berguna untuk memantau agar tidak kehabisan token.
    """
    stats = get_usage_stats()
    return {
        **stats,
        "tip": (
            "Jika token mendekati batas, aktifkan fallback dengan: "
            "POST /api/ai/switch body={provider: 'ollama'} untuk lokal, "
            "atau kurangi ai_max_findings_per_call di .env"
        ),
    }


@router.post("/usage/reset")
def reset_ai_usage():
    """Reset counter penggunaan AI sesi ini."""
    reset_usage()
    return {"message": "Usage counter direset"}


@router.post("/test")
async def test_ai(prompt: str = "Jawab: 1+1=?"):
    """Test koneksi ke provider AI yang aktif."""
    try:
        result = await call_ai(prompt)
        return {"provider": settings.ai_provider, "response": result, "status": "ok"}
    except Exception as e:
        raise HTTPException(500, f"AI gagal: {str(e)}")
