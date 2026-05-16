"""
app/routers/ai_config.py
------------------------
Ganti AI provider secara runtime tanpa restart server.
Switch provider: admin only.
Usage stats dan test: semua authenticated user.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.auth import CurrentUser, require_admin
from app.services.ai_service import (
    AIConfig, get_ai_config, get_usage_stats,
    reset_usage_stats, set_ai_config, test_ai_connection,
)

router = APIRouter(prefix="/api/ai", tags=["AI Config"])


class SwitchRequest(BaseModel):
    provider:  str               # gemini | claude | openai | ollama
    api_key:   str | None = None
    base_url:  str | None = None
    model:     str | None = None
    max_tokens: int = 1000


@router.get("/config")
def get_config(user: CurrentUser):
    """Cek konfigurasi AI provider aktif saat ini."""
    cfg = get_ai_config()
    return {
        "message": "OK",
        "data": {
            "provider":   cfg.provider,
            "model":      cfg.model,
            "max_tokens": cfg.max_tokens,
            # Jangan expose api_key
        }
    }


@router.post("/switch")
def switch_provider(body: SwitchRequest, user: CurrentUser):
    """
    Ganti AI provider runtime (tanpa restart server).
    Admin only.
    """
    require_admin(user)

    valid_providers = {"gemini", "claude", "openai", "ollama"}
    if body.provider not in valid_providers:
        raise HTTPException(
            status_code=422,
            detail=f"Provider tidak valid. Pilihan: {valid_providers}",
        )

    new_config = AIConfig(
        provider   = body.provider,
        api_key    = body.api_key,
        base_url   = body.base_url,
        model      = body.model,
        max_tokens = body.max_tokens,
    )
    set_ai_config(new_config)

    return {
        "message": f"AI provider berhasil diganti ke '{body.provider}'.",
        "data":    {"provider": body.provider, "model": body.model},
    }


@router.post("/test")
def test_connection(user: CurrentUser, prompt: str = "Halo, tes koneksi AI."):
    """Test koneksi ke AI provider aktif."""
    try:
        response = test_ai_connection(prompt)
        return {"message": "Koneksi AI berhasil.", "data": {"response": response}}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"AI tidak dapat dihubungi: {e}")


@router.get("/usage")
def usage_stats(user: CurrentUser):
    """Pantau penggunaan token AI di sesi ini."""
    return {"message": "OK", "data": get_usage_stats()}


@router.post("/usage/reset")
def reset_usage(user: CurrentUser):
    """Reset counter penggunaan token. Admin only."""
    require_admin(user)
    reset_usage_stats()
    return {"message": "Usage counter direset.", "data": get_usage_stats()}
