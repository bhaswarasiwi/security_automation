"""
app/main.py (PATCHED)
---------------------
Perubahan dari versi lama:
1. CORS: tambah Vercel production domain
2. CORS: baca dari ENV agar fleksibel per environment
3. Semua router sudah siap terima Depends(get_current_user)
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import targets, scan, sessions, methods, results, report, ai_config

app = FastAPI(
    title="Security Automation API",
    description="Agentic Security Tools — FastAPI + Supabase + AI",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ---------------------------------------------------------------------
# CORS — baca dari ENV, fallback ke defaults
# Set ALLOWED_ORIGINS di Render Dashboard (pisahkan dengan koma):
#   https://nama-project.vercel.app,http://localhost:3000
# ---------------------------------------------------------------------
_origins_env = os.environ.get("ALLOWED_ORIGINS", "")

ALLOWED_ORIGINS: list[str] = [
    origin.strip()
    for origin in _origins_env.split(",")
    if origin.strip()
] or [
    # Default untuk development lokal
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,   # Wajib True agar browser kirim cookie + Authorization header
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Session-ID"],  # Expose custom header ke FE jika dibutuhkan
)

# ---------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------
app.include_router(targets.router)
app.include_router(scan.router)
app.include_router(sessions.router)
app.include_router(methods.router)
app.include_router(results.router)
app.include_router(report.router)
app.include_router(ai_config.router)


@app.get("/", tags=["Health"])
def root():
    return {
        "status":  "ok",
        "version": "1.0.0",
        "message": "Security Automation API",
    }


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}
