from fastapi import APIRouter
from datetime import datetime, timezone

router = APIRouter()

_start_time = datetime.now(timezone.utc)

@router.get("/ping")
def ping():
    """
    Endpoint khusus UptimeRobot — dipanggil setiap 10 menit.
    Ringan, tidak sentuh DB atau AI sama sekali.
    """
    uptime_seconds = (datetime.now(timezone.utc) - _start_time).total_seconds()
    return {
        "status": "ok",
        "uptime_seconds": int(uptime_seconds),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
