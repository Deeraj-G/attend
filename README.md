# Attend

## Prerequisites

- Python 3.13 (see `.python-version`)
- Node 22 (see `.nvmrc`)

## Setup

```bash
# Backend: one shared venv at the repo root
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Frontend
cd frontend && npm ci
```

## Run

```bash
# Backend (from repo root, venv active) -> http://localhost:8000
uvicorn backend.app.main:app --reload

# Frontend (in frontend/) -> http://localhost:5173, proxies /api -> :8000
npm run dev
```

## Docker (local testing)

Runs the backend, frontend, and the two on-device models as separate containers.
Nimble and BFL are hosted APIs, not local models — the backend calls them
directly using the keys in `.env.dev`, no container needed for those.

```bash
# One-time: fetch the LFM2.5-2.6B GGUF weights (~1.6GB, not committed to git)
./scripts/fetch_models.sh

# LFM2.5-Audio-1.5B: downloads from Hugging Face by default, or put a
# checkpoint at ./models/lfm-audio and set LFM_AUDIO_MODEL_PATH=/models

docker compose up --build
```

| Service | Port | Notes |
|---|---|---|
| frontend | 5173 | Vite dev server |
| backend | 8000 | FastAPI with autoreload |
| lfm | 8081 | llama.cpp server, OpenAI-compatible API |
| lfm-audio | 8090 | `POST /transcribe`, `POST /synthesize` |

`backend/` and `frontend/` are bind-mounted, so edits on the host reload live.
`LFM_BASE_URL` and `LFM_AUDIO_BASE_URL` are passed to the backend container for
when `LFMClient`/`LFMAudioClient` are implemented to call these servers over HTTP.

## Adding dependencies

- Python: `pip install <pkg>`, then pin the exact version in `requirements.txt`.
- Frontend: `npm install <pkg>` in `frontend/`, and commit `package-lock.json`.
