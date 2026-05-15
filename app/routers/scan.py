"""
app/routers/scan.py (PATCHED — multi-tenant)
--------------------------------------------
Perubahan dari versi lama:
- Wajib login
- create_session inject user_id
- Status check verifikasi kepemilikan session
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException

from app.agent.runner import ScanConfig
from app.agent.async_runner import AsyncAgentRunner
from app.agent.repository import ScanRepository
from app.api.dependencies import get_repository
from app.api.schemas import ScanRequest, MessageResponse
from app.api.ws_manager import ws_manager
from app.core.auth import CurrentUser

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/scan", tags=["Scan"])


async def _run_scan_background(
    config: ScanConfig,
    session_id: str,
) -> None:
    runner = AsyncAgentRunner()

    async def push(event: str, data: dict) -> None:
        await ws_manager.push(session_id, event, data)

    try:
        await runner.run(config=config, session_id=session_id, ws_push=push)
    except Exception as e:
        logger.error("Background scan error: %s", e, exc_info=True)


@router.post("", response_model=MessageResponse, status_code=202)
async def run_scan(
    body: ScanRequest,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser,
    repo: ScanRepository = Depends(get_repository),
):
    """
    Jalankan scan baru (202 Accepted — scan jalan di background).
    Subscribe /ws/{session_id} untuk live progress.
    """
    # Resolve dan validasi target
    if body.target_id:
        # Verifikasi kepemilikan target
        target = repo.get_target(body.target_id, user_id=current_user.user_id)
        if not target:
            raise HTTPException(status_code=404, detail="Target tidak ditemukan.")
        target_id = body.target_id
        base_url  = target["base_url"]
    else:
        # Auto-create target untuk manual URL, langsung assign ke user
        from urllib.parse import urlparse
        hostname = urlparse(body.manual_url).hostname or body.manual_url
        target = repo.create_target(
            nama      = f"[Manual] {hostname}",
            jenis     = "web",
            base_url  = body.manual_url,
            deskripsi = "Auto-created dari manual URL input.",
            user_id   = current_user.user_id,   # ← assign ke user
        )
        target_id = target["id"]
        base_url  = body.manual_url

    # Buat session dengan user_id
    session = repo.create_session(
        target_id  = target_id,
        user_id    = current_user.user_id,    # ← inject user_id
        nama       = body.session_nama or f"Scan — {base_url}",
    )
    session_id = session["id"]

    config = ScanConfig(
        target_id      = target_id,
        execution_mode = body.execution_mode,
        timeout        = body.timeout,
        session_nama   = body.session_nama,
    )

    background_tasks.add_task(
        _run_scan_background,
        config     = config,
        session_id = session_id,
    )

    return MessageResponse(
        message = "Scan dimulai. Subscribe ke WebSocket untuk live progress.",
        data    = {
            "session_id": session_id,
            "target_url": base_url,
            "ws_url":     f"/ws/{session_id}",
        }
    )


@router.get("/{session_id}/status", response_model=MessageResponse)
def get_scan_status(
    session_id: str,
    current_user: CurrentUser,
    repo: ScanRepository = Depends(get_repository),
):
    """Cek status scan. Hanya milik user sendiri."""
    session = repo.get_session(session_id, user_id=current_user.user_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session tidak ditemukan.")

    data = {
        "session_id":  session_id,
        "status":      session["status"],
        "started_at":  session.get("started_at"),
        "finished_at": session.get("finished_at"),
    }

    if session["status"] in ("completed", "failed"):
        data["summary"] = repo.get_summary_by_session(session_id)

    return MessageResponse(message="OK", data=data)
