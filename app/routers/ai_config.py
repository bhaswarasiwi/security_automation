from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Literal, Optional
from app.core.config import settings
from app.services.ai_service import get_usage_stats, reset_usage, call_ai

router = APIRouter()


class SwitchProviderRequest(BaseModel):
    provider: Literal["gemini", "claude", "openai", "ollama"]
    api_key: Optional[str] = None
    model: Optional[str] = None
    base_url: Optional[str] = None


@router.get("/provider")
def get_current_provider():
    return {
        "provider": settings.ai_provider,
        "gemini_model": settings.gemini_model,
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
    Ganti AI provider secara runtime tanpa restart.

    Contoh pindah ke akun kantor/klien:
    - OpenAI kantor: provider=openai, api_key=..., base_url=https://ai.kantor.com/v1
    - Gemini gratis: provider=gemini, api_key=AIza...
    - Offline: provider=ollama
    """
    settings.ai_provider = body.provider

    if body.provider == "gemini":
        if body.api_key: settings.gemini_api_key = body.api_key
        if body.model:   settings.gemini_model = body.model

    if body.provider == "claude":
        if body.api_key: settings.anthropic_api_key = body.api_key
        if body.model:   settings.claude_model = body.model

    if body.provider == "openai":
        if body.api_key:  settings.openai_api_key = body.api_key
        if body.model:    settings.openai_model = body.model
        if body.base_url: settings.openai_base_url = body.base_url

    if body.provider == "ollama":
        if body.base_url: settings.ollama_base_url = body.base_url
        if body.model:    settings.ollama_model = body.model

    return {"message": f"Provider berhasil diganti ke: {body.provider}", "provider": settings.ai_provider}


@router.get("/usage")
def ai_usage():
    stats = get_usage_stats()
    limits = {
        "gemini": "1.500 request/hari, 1 juta token/menit (gratis)",
        "claude": "Sesuai kredit Anthropic",
        "openai": "Sesuai kredit OpenAI",
        "ollama": "Tidak terbatas (lokal)",
    }
    return {
        **stats,
        "limit_info": limits.get(settings.ai_provider, "-"),
        "tip": "Jika limit habis, switch ke ollama: POST /api/ai/switch {provider: 'ollama'}",
    }


@router.post("/usage/reset")
def reset_ai_usage():
    reset_usage()
    return {"message": "Usage counter direset"}


@router.post("/test")
async def test_ai(prompt: str = "Jawab singkat: 1+1 berapa?"):
    try:
        result = await call_ai(prompt)
        return {"provider": settings.ai_provider, "response": result, "status": "ok"}
    except Exception as e:
        raise HTTPException(500, f"AI gagal: {str(e)}")
