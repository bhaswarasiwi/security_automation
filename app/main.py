"""
app/main.py
-----------
Entry point FastAPI.

Perubahan dari versi lama:
  - CORS baca dari ENV (ALLOWED_ORIGINS)
  - /docs, /redoc, /openapi.json dikunci di production (ENVIRONMENT=production)
  - Semua router sudah siap dengan auth middleware
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.routers import ai_config, report, results, scan, targets

settings = get_settings()

app = FastAPI(
    title       = "Bug Bounty Automation API",
    description = "FastAPI + Supabase + AI — Agentic Security Automation",
    version     = "2.0.0",
    # Kunci docs di production agar attack surface tidak terekspos
    docs_url    = None if settings.is_production else "/docs",
    redoc_url   = None if settings.is_production else "/redoc",
    openapi_url = None if settings.is_production else "/openapi.json",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# Set ALLOWED_ORIGINS di Render Dashboard (pisah koma):
#   https://nama-app.vercel.app,http://localhost:3000
app.add_middleware(
    CORSMiddleware,
    allow_origins     = settings.cors_origins,
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(targets.router)
app.include_router(scan.router)
app.include_router(results.router)
app.include_router(report.router)
app.include_router(ai_config.router)


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/", tags=["Health"])
def root():
    return {"status": "ok", "version": "2.0.0"}


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}

@app.get("/ping", tags=["Health"])
def ping():
    return {"status": "ok"}
