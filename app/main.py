from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import targets, scan, results, report, ai_config, uptime
from app.core.config import settings

app = FastAPI(
    title="Bug Bounty Automation API",
    version="1.0.0",
    description="Automated security scanning with AI triage — swappable AI provider",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Ganti dengan domain spesifik di production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(targets.router,    prefix="/api/targets",   tags=["Targets"])
app.include_router(scan.router,       prefix="/api/scan",      tags=["Scanning"])
app.include_router(results.router,    prefix="/api/results",   tags=["Results"])
app.include_router(report.router,     prefix="/api/report",    tags=["Report"])
app.include_router(ai_config.router,  prefix="/api/ai",        tags=["AI Config"])
app.include_router(uptime.router,     prefix="",               tags=["Uptime"])

@app.get("/")
def root():
    return {
        "status": "ok",
        "version": "1.0.0",
        "ai_provider": settings.ai_provider,
        "docs": "/docs",
    }

@app.get("/health")
def health():
    return {"status": "healthy"}
