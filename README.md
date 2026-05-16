# 🛡️ Bug Bounty Automation API

FastAPI + Supabase + AI (swappable) untuk otomasi recon dan vulnerability scanning.
Multi-tenant: setiap user hanya bisa akses data miliknya sendiri.

---

## Struktur Project

```
bugbounty-api/
├── app/
│   ├── __init__.py
│   ├── main.py                    # Entry point FastAPI
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py              # Semua konfigurasi (ENV-based, pydantic-settings)
│   │   ├── supabase.py            # Supabase client singleton (service_role)
│   │   └── auth.py                # JWT verification middleware (BARU)
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── targets.py             # CRUD target & endpoint (auth + user isolation)
│   │   ├── scan.py                # Trigger scan, cek status, AI triage
│   │   ├── results.py             # Ambil hasil scan
│   │   ├── report.py              # Generate laporan Markdown + AI analysis
│   │   └── ai_config.py           # Ganti AI provider runtime (admin only untuk switch)
│   └── services/
│       ├── __init__.py
│       ├── scan_service.py        # Runner scan — load methods dari DB via whitelist registry
│       └── ai_service.py          # Gemini / Claude / OpenAI / Ollama
├── scripts/
│   └── install_tools.sh           # Install scanning tools di Render
├── fix_admin_role.sql             # Fix SQL untuk set user admin
├── render.yaml                    # Konfigurasi deploy Render
├── requirements.txt
└── .env.example
```

---

## Arsitektur Keamanan

### Multi-tenancy
- Setiap user hanya bisa akses data miliknya (`user_id` di tabel `target` dan `scan_session`)
- Row Level Security (RLS) aktif di Supabase — data terisolasi di level database
- Backend pakai `service_role` key (bypass RLS untuk operasi sistem)
- Frontend pakai `anon` key (RLS aktif, data difilter otomatis)

### Auth Flow
```
FE login via Supabase → dapat access_token (JWT)
FE kirim: Authorization: Bearer <access_token>
BE verify token ke Supabase Auth
BE inject user ke handler via Depends(get_current_user)
```

### Scanner Whitelist
`function_map` di tabel `hack_methods` harus PERSIS sama dengan key di `SCANNER_REGISTRY`.
Tidak ada eval atau dynamic import — hanya dict statis Python.

---

## Deploy ke Render

### 1. Environment Variables (wajib semua diisi)

| Key | Value | Keterangan |
|-----|-------|-----------|
| `SUPABASE_URL` | `https://xxxx.supabase.co` | URL project Supabase |
| `SUPABASE_KEY` | `eyJ...` | **service_role** key (bukan anon!) |
| `ALLOWED_ORIGINS` | `https://app.vercel.app,http://localhost:3000` | Domain FE, pisah koma |
| `ENVIRONMENT` | `production` | Lock `/docs` di production |
| `AI_PROVIDER` | `gemini` | Provider AI aktif |
| `GEMINI_API_KEY` | `AIza...` | API key Google AI Studio |
| `GEMINI_MODEL` | `gemini-2.0-flash` | Model Gemini |
| `SECRET_KEY` | string acak panjang | Untuk signing internal |

### 2. Build & Start Command
```
Build:  pip install -r requirements.txt && bash scripts/install_tools.sh
Start:  uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

---

## Cara Ganti AI Provider

### Via ENV (permanen, butuh restart)
```bash
# Di Render Dashboard → Environment:
AI_PROVIDER=gemini
GEMINI_API_KEY=AIza...

# Atau ke Claude:
AI_PROVIDER=claude
ANTHROPIC_API_KEY=sk-ant-...

# Atau ke OpenAI:
AI_PROVIDER=openai
OPENAI_API_KEY=sk-...
```

### Via API (runtime, tanpa restart) — Admin Only
```bash
BASE=https://security-automation-fmhl.onrender.com
TOKEN=<supabase_access_token_admin>

# Pindah ke Gemini
curl -X POST $BASE/api/ai/switch \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"provider": "gemini", "api_key": "AIza...", "model": "gemini-2.0-flash"}'

# Pindah ke Claude
curl -X POST $BASE/api/ai/switch \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"provider": "claude", "api_key": "sk-ant-..."}'

# Pindah ke Ollama (lokal/kantor)
curl -X POST $BASE/api/ai/switch \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"provider": "ollama", "base_url": "http://server:11434", "model": "llama3"}'
```

---

## Set User sebagai Admin

```sql
-- Di Supabase SQL Editor:

-- 1. Cek UUID user
SELECT id, email FROM auth.users;

-- 2. Set admin
SELECT public.set_user_role('uuid-user-di-sini', 'admin');

-- 3. Verifikasi
SELECT id, email, raw_app_meta_data FROM auth.users;
-- raw_app_meta_data harus mengandung: {"role": "admin"}
```

---

## Pantau Penggunaan AI

```bash
TOKEN=<access_token>
BASE=https://security-automation-fmhl.onrender.com

# Cek usage
curl $BASE/api/ai/usage -H "Authorization: Bearer $TOKEN"

# Test koneksi AI
curl -X POST "$BASE/api/ai/test?prompt=halo" -H "Authorization: Bearer $TOKEN"

# Reset counter (admin only)
curl -X POST $BASE/api/ai/usage/reset -H "Authorization: Bearer $TOKEN"
```

---

## Quick Start API

Semua endpoint butuh `Authorization: Bearer <token>`. Token didapat dari Supabase Auth setelah login.

```bash
BASE=https://security-automation-fmhl.onrender.com
TOKEN=<supabase_access_token>

# 1. Tambah target
curl -X POST $BASE/api/targets \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"nama": "Target 1", "jenis": "web", "base_url": "https://example.com"}'

# 2. List targets
curl $BASE/api/targets -H "Authorization: Bearer $TOKEN"

# 3. Mulai scan
curl -X POST $BASE/api/scan/start \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"target_id": "uuid-target", "use_ai_triage": true}'

# 4. Pantau status
curl $BASE/api/scan/status/{session_id} -H "Authorization: Bearer $TOKEN"

# 5. Lihat hasil
curl $BASE/api/results/{session_id} -H "Authorization: Bearer $TOKEN"

# 6. Lihat findings saja (yang fail)
curl "$BASE/api/results/{session_id}/findings?severity=high" -H "Authorization: Bearer $TOKEN"

# 7. AI triage manual
curl -X POST $BASE/api/scan/triage/{session_id} -H "Authorization: Bearer $TOKEN"

# 8. Generate laporan lengkap
curl "$BASE/api/report/{session_id}?use_ai=true" -H "Authorization: Bearer $TOKEN"
```

---

## Catatan Penting

- **Hanya scan target yang sudah ada izin (bug bounty program resmi)**
- Rate limit nuclei sudah diset ke 10 req/detik (etis)
- Free plan Render: 512MB RAM, sleep setelah 15 menit idle
- `/docs` dikunci di production (`ENVIRONMENT=production`) — akses Swagger hanya di development
- `service_role` key **jangan pernah** diekspos ke FE atau response API
