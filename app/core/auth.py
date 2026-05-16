"""
app/core/auth.py
----------------
Dependency FastAPI untuk verifikasi JWT Supabase.

Flow:
  FE login via Supabase → dapat access_token
  FE kirim: Authorization: Bearer <access_token>
  BE extract token → verify ke Supabase Auth
  BE inject AuthenticatedUser ke handler via Depends(get_current_user)
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.supabase import get_supabase

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=True)


class AuthenticatedUser:
    def __init__(self, user_id: str, email: str | None, app_metadata: dict):
        self.user_id       = user_id
        self.email         = email
        self._app_metadata = app_metadata

    @property
    def is_admin(self) -> bool:
        """True jika user punya role admin di app_metadata Supabase."""
        return self._app_metadata.get("role") == "admin"

    def __repr__(self) -> str:
        return f"AuthenticatedUser(id={self.user_id[:8]}…, admin={self.is_admin})"


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
) -> AuthenticatedUser:
    """
    Verify JWT Supabase dan kembalikan user.
    Gunakan sebagai dependency di router:

        @router.get("/targets")
        def list_targets(user: CurrentUser, ...):
            ...
    """
    token = credentials.credentials
    sb    = get_supabase()

    try:
        resp = sb.auth.get_user(token)
        user = resp.user
        if not user:
            raise ValueError("user null")
    except Exception as exc:
        logger.warning("Token verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token tidak valid atau sudah kedaluwarsa. Silakan login ulang.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return AuthenticatedUser(
        user_id       = user.id,
        email         = user.email,
        app_metadata  = user.app_metadata or {},
    )


def require_admin(user: "AuthenticatedUser") -> None:
    """Helper: raise 403 jika bukan admin. Panggil di awal handler admin-only."""
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Akses ditolak. Hanya admin yang dapat melakukan operasi ini.",
        )


# Type alias — pakai ini di semua router
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
