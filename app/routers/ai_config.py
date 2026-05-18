"""
app/routers/ai_config.py
------------------------
Per-user AI config. Setiap user bisa set provider dan API key sendiri.
API key dienkripsi di BE sebelum disimpan — FE tidak pernah terima nilai key.
"""

from __future__ import annotations
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, field_validator
from app.core.auth import CurrentUser
from app.core.supabase import get_supabase
from app.core.encryption import encrypt_api_key, decrypt_api_key
from app.services.ai_service import AIConfig, set_ai_config, get_ai_config, get_usage_stats, reset_usage_stats, test_ai_connection
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ai", tags=["AI Config"])

VALID_PROVIDERS = {"gemini", "claude", "openai", "ollama"}

DEFAULT_MODELS = {
    "gemini": "gemini-2.0-flash",
    "claude": "claude-3-5-haiku-20241022",
    "openai": "gpt-4o-mini",
    "ollama": "llama3",
}


class SaveConfigRequest(BaseModel):
    provider: str
    api_key: str | None = None   # None = pakai server default / tidak ubah key
    base_url: str | None = None
    model: str | None = None
    max_tokens: int = 1000

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        if v not in VALID_PROVIDERS:
            raise ValueError(f"Provider tidak valid. Pilihan: {VALID_PROVIDERS}")
        return v

    @field_validator("max_tokens")
    @classmethod
    def validate_tokens(cls, v: int) -> int:
        if not (100 <= v <= 8000):
            raise ValueError("max_tokens harus antara 100 dan 8000")
        return v


@router.get("/config")
async def get_config(user: CurrentUser):
    """
    Ambil config AI user saat ini.
    api_key TIDAK dikembalikan — hanya boolean has_key.
    """
    sb = get_supabase()
    row = sb.table("user_ai_config") \
            .select("provider, model, base_url, max_tokens, api_key_enc, is_active") \
            .eq("user_id", str(user.user_id)) \
            .maybe_single() \
            .execute()

    if row.data:
        cfg = row.data
        return {
            "message": "OK",
            "data": {
                "provider":   cfg["provider"],
                "model":      cfg["model"] or DEFAULT_MODELS.get(cfg["provider"]),
                "base_url":   cfg["base_url"],
                "max_tokens": cfg["max_tokens"],
                "has_key":    bool(cfg.get("api_key_enc")),
                "is_active":  cfg["is_active"],
                "source":     "user",  # config dari user, bukan server ENV
            }
        }

    # Fallback: kembalikan config server (dari ENV)
    server_cfg = get_ai_config()
    return {
        "message": "OK",
        "data": {
            "provider":   server_cfg.provider,
            "model":      server_cfg.model or DEFAULT_MODELS.get(server_cfg.provider),
            "base_url":   server_cfg.base_url,
            "max_tokens": server_cfg.max_tokens,
            "has_key":    bool(server_cfg.api_key),
            "is_active":  True,
            "source":     "server",  # config dari ENV server
        }
    }


@router.post("/config")
async def save_config(body: SaveConfigRequest, user: CurrentUser):
    """
    Simpan atau update konfigurasi AI user.
    API key dienkripsi sebelum insert ke DB.
    """
    sb = get_supabase()

    # Cek apakah sudah ada config untuk user ini
    existing = sb.table("user_ai_config") \
                 .select("id, api_key_enc") \
                 .eq("user_id", str(user.user_id)) \
                 .maybe_single() \
                 .execute()

    upsert_data: dict = {
        "user_id":    str(user.user_id),
        "provider":   body.provider,
        "model":      body.model or DEFAULT_MODELS.get(body.provider),
        "base_url":   body.base_url,
        "max_tokens": body.max_tokens,
        "is_active":  True,
    }

    # Enkripsi key baru jika diberikan
    if body.api_key and body.api_key.strip():
        try:
            upsert_data["api_key_enc"] = encrypt_api_key(body.api_key.strip())
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Gagal mengenkripsi API key: {e}")
    elif existing.data:
        # Tidak ada key baru → pertahankan key lama
        pass

    # Upsert (insert atau update)
    result = sb.table("user_ai_config").upsert(upsert_data, on_conflict="user_id").execute()

    if not result.data:
        raise HTTPException(status_code=500, detail="Gagal menyimpan konfigurasi")

    return {
        "message": f"Konfigurasi AI berhasil disimpan ({body.provider})",
        "data": {
            "provider":  body.provider,
            "model":     upsert_data["model"],
            "has_key":   "api_key_enc" in upsert_data or (existing.data and existing.data.get("api_key_enc")),
            "source":    "user",
        }
    }


@router.delete("/config/key")
async def delete_api_key(user: CurrentUser):
    """Hapus API key user — permanen. User akan fallback ke server config."""
    sb = get_supabase()
    sb.table("user_ai_config") \
      .update({"api_key_enc": None}) \
      .eq("user_id", str(user.user_id)) \
      .execute()
    return {"message": "API key berhasil dihapus secara permanen."}


@router.post("/test")
async def test_connection(user: CurrentUser, prompt: str = "Halo, tes koneksi AI."):
    """Test koneksi ke AI provider menggunakan config user (atau server jika belum set)."""
    sb = get_supabase()
    row = sb.table("user_ai_config") \
            .select("provider, model, base_url, max_tokens, api_key_enc") \
            .eq("user_id", str(user.user_id)) \
            .maybe_single() \
            .execute()

    if row.data and row.data.get("api_key_enc"):
        try:
            api_key = decrypt_api_key(row.data["api_key_enc"])
        except ValueError as e:
            raise HTTPException(status_code=500, detail=str(e))

        user_cfg = AIConfig(
            provider   = row.data["provider"],
            api_key    = api_key,
            base_url   = row.data.get("base_url"),
            model      = row.data.get("model"),
            max_tokens = row.data.get("max_tokens", 1000),
        )
        # Set config sementara untuk test — tidak persistent ke global
        original = get_ai_config()
        set_ai_config(user_cfg)
        try:
            response = test_ai_connection(prompt)
        except Exception as e:
            set_ai_config(original)
            raise HTTPException(status_code=503, detail=f"AI tidak dapat dihubungi: {e}")
        set_ai_config(original)
    else:
        try:
            response = test_ai_connection(prompt)
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"AI tidak dapat dihubungi: {e}")

    return {"message": "Koneksi AI berhasil.", "data": {"response": response}}


@router.get("/usage")
async def usage_stats(user: CurrentUser):
    return {"message": "OK", "data": get_usage_stats()}


@router.post("/usage/reset")
async def reset_usage(user: CurrentUser):
    reset_usage_stats()
    return {"message": "Usage counter direset.", "data": get_usage_stats()}
