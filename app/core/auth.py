"""
app/core/auth.py
----------------
Middleware autentikasi FastAPI untuk verifikasi JWT Supabase.

Cara kerja:
1. FE kirim request dengan header: Authorization: Bearer <supabase_access_token>
2. FastAPI extract token dari header
3. Kita verifikasi token ke Supabase (supabase.auth.get_user(token))
4. Jika valid, inject user info ke handler via Depends(get_current_user)
5. Jika invalid/expired, return 401 Unauthorized langsung

PENTING:
- Backend tetap pakai service_role key untuk OPERASI DB (bypass RLS)
- Verifikasi JWT dilakukan terpisah ke Supabase Auth endpoint
- user_id dari JWT inilah yang kita insert ke kolom user_id di setiap record baru

Pasang di requirements.txt:
  python-jose[cryptography]>=3.3.0
  (sudah ada via supabase client)
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.supabase import get_supabase

logger = logging.getLogger(__name__)

# FastAPI security scheme — otomatis baca header "Authorization: Bearer ..."
_bearer_scheme = HTTPBearer(auto_error=True)


class AuthenticatedUser:
    """Representasi user yang sudah terverifikasi."""

    def __init__(self, user_id: str, email: str | None = None, metadata: dict | None = None):
        self.user_id  = user_id
        self.email    = email
        self.metadata = metadata or {}

    def __repr__(self) -> str:
        return f"AuthenticatedUser(id={self.user_id[:8]}..., email={self.email})"


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer_scheme)],
) -> AuthenticatedUser:
    """
    FastAPI dependency: verifikasi JWT Supabase dan kembalikan user.

    Usage di router:
        @router.get("/targets")
        def list_targets(
            current_user: AuthenticatedUser = Depends(get_current_user),
            repo: ScanRepository = Depends(get_repository),
        ):
            targets = repo.get_targets_by_user(current_user.user_id)
            ...
    """
    token = credentials.credentials

    # Verifikasi token ke Supabase Auth
    # Supabase akan reject token expired/invalid/revoked
    supabase = get_supabase()

    try:
        response = supabase.auth.get_user(token)
        user = response.user

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token tidak valid atau sudah kedaluwarsa.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return AuthenticatedUser(
            user_id  = user.id,
            email    = user.email,
            metadata = user.user_metadata or {},
        )

    except HTTPException:
        raise  # Re-raise HTTP exceptions langsung
    except Exception as exc:
        logger.warning("Token verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autentikasi gagal. Silakan login ulang.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


# Shorthand type alias untuk dipakai di semua router
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
