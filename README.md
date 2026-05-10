# 🦞 Bug Bounty Automation API

FastAPI + Supabase + AI (swappable) untuk otomasi recon dan vulnerability scanning.

---

## Struktur Project

```
bugbounty-api/
├── app/
│   ├── main.py                # Entry point FastAPI
│   ├── core/
│   │   ├── config.py          # Semua konfigurasi (ENV-based)
│   │   └── supabase.py        # Supabase client
│   ├── routers/
│   │   ├── targets.py         # CRUD target & endpoint
│   │   ├── scan.py            # Trigger scan, cek status
│   │   ├── results.py         # Ambil hasil
│   │   ├── report.py          # Generate laporan
│   │   └── ai_config.py       # Ganti AI provider runtime
│   └── services/
│       ├── scan_service.py    # subfinder + httpx + nuclei
│       └── ai_service.py      # Claude / OpenAI / Ollama
├── scripts/
│   └── install_tools.sh       # Install scanning tools di Render
├── render.yaml                # Konfigurasi deploy Render
├── requirements.txt
└── .env.example
```

---

## Deploy ke Render (step by step)

### 1. Push ke GitHub
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/username/bugbounty-api.git
git push -u origin main
```

### 2. Buat Web Service di Render
1. Login ke [render.com](https://render.com)
2. Klik **New → Web Service**
3. Hubungkan GitHub repo kamu
4. Render otomatis detect `render.yaml` — konfirmasi settings:
   - **Region**: Singapore (paling dekat Indonesia)
   - **Build Command**: `pip install -r requirements.txt && bash scripts/install_tools.sh`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Plan**: Free (atau Starter $7/bln untuk production)

### 3. Set Environment Variables di Render Dashboard
Masuk ke service → **Environment** → tambahkan:

| Key | Value |
|-----|-------|
| `SUPABASE_URL` | URL Supabase kamu |
| `SUPABASE_KEY` | service_role key dari Supabase |
| `AI_PROVIDER` | `claude` |
| `ANTHROPIC_API_KEY` | API key Claude |
| `SECRET_KEY` | string acak panjang |

### 4. Deploy
Render otomatis deploy setiap push ke `main`.
Akses API kamu di: `https://bugbounty-api.onrender.com`

---

## Cara Ganti AI Provider

### Via ENV (permanen)
Edit di Render Dashboard → Environment:
```
AI_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1  # atau proxy kantor
```

### Via API (runtime, tanpa restart)
```bash
# Pindah ke OpenAI
curl -X POST https://bugbounty-api.onrender.com/api/ai/switch \
  -H "Content-Type: application/json" \
  -d '{"provider": "openai", "api_key": "sk-...", "base_url": "https://api.openai.com/v1"}'

# Pindah ke Claude
curl -X POST https://bugbounty-api.onrender.com/api/ai/switch \
  -d '{"provider": "claude", "api_key": "sk-ant-..."}'

# Pindah ke Ollama (lokal/kantor, tidak butuh API key)
curl -X POST https://bugbounty-api.onrender.com/api/ai/switch \
  -d '{"provider": "ollama", "base_url": "http://ollama-server:11434", "model": "llama3"}'

# Proxy OpenAI kantor
curl -X POST https://bugbounty-api.onrender.com/api/ai/switch \
  -d '{"provider": "openai", "api_key": "key-kantor", "base_url": "https://ai.kantor.com/v1"}'
```

---

## Pantau Penggunaan AI (jaga agar tidak boros token)

```bash
# Cek usage sesi ini
curl https://bugbounty-api.onrender.com/api/ai/usage

# Reset counter
curl -X POST https://bugbounty-api.onrender.com/api/ai/usage/reset

# Test koneksi AI
curl -X POST "https://bugbounty-api.onrender.com/api/ai/test?prompt=hello"
```

Jika token hampir habis:
1. Kurangi `AI_MAX_FINDINGS_PER_CALL` (default: 10)
2. Kurangi `AI_MAX_TOKENS` (default: 1000)
3. Atau pindah ke Ollama (lokal, gratis)

---

## Quick Start API

```bash
BASE=https://bugbounty-api.onrender.com

# 1. Tambah target
curl -X POST $BASE/api/targets \
  -H "Content-Type: application/json" \
  -d '{"nama": "Target 1", "jenis": "web", "base_url": "https://example.com"}'

# 2. Mulai scan (langsung return session_id)
curl -X POST $BASE/api/scan/start \
  -d '{"target_id": "uuid-target", "use_ai_triage": true}'

# 3. Pantau status
curl $BASE/api/scan/status/{session_id}

# 4. Lihat hasil
curl $BASE/api/results/{session_id}

# 5. AI triage
curl -X POST $BASE/api/scan/triage/{session_id}

# 6. Generate laporan
curl "$BASE/api/report/{session_id}?use_ai=true"
```

---

## Catatan Penting

- **Hanya scan target yang sudah ada izin (bug bounty program resmi)**
- Rate limit nuclei sudah diset ke 10 req/detik (etis)
- Free plan Render: 512MB RAM, sleep setelah 15 menit idle
- Upgrade ke Starter ($7/bln) untuk: lebih RAM, no sleep, custom domain
