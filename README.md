# longhorizon

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

## Adding dependencies

- Python: `pip install <pkg>`, then pin the exact version in `requirements.txt`.
- Frontend: `npm install <pkg>` in `frontend/`, and commit `package-lock.json`.
