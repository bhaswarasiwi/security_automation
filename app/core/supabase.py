"""
app/core/supabase.py
--------------------
Supabase client singleton menggunakan service_role key.
Service_role key bypass RLS — aman di backend, JANGAN expose ke FE.
"""

from __future__ import annotations

from functools import lru_cache

from supabase import Client, create_client

from app.core.config import get_settings


@lru_cache(maxsize=1)
def get_supabase() -> Client:
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_key)
