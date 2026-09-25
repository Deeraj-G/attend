# AGENTS.md

Guidance for AI coding agents working in this repository. `CLAUDE.md` is a symlink to this file.

## Rules

- **No AI attribution.** Never add `Co-Authored-By: Claude ...` (or any other AI co-author) trailers to commits. Never add "Generated with Claude Code" or similar AI attribution text to commit messages, PR descriptions, code, comments or docs. Commits are authored by the human committer only.

## Project

Procedure explainer video agent on a Manage-Execute-Audit harness. Design decisions live in [docs/adr/](docs/adr/); read the relevant ADR before changing the harness.

- **Backend:** FastAPI, Python 3.13, in [backend/](backend/). Shared venv at the repo root (`.venv`), dependencies pinned in [requirements.txt](requirements.txt).
- **Frontend:** React + TypeScript + Vite, in [frontend/](frontend/). Commit `package-lock.json`.

## Commands

```bash
source .venv/bin/activate && pip install -r requirements.txt   # backend deps
uvicorn backend.app.main:app --reload                           # backend on :8000
python -m pytest backend/tests                                  # backend tests
cd frontend && npm ci && npm run dev                            # frontend on :5173 (proxies /api -> :8000)
```

## Backend layout

- `api/routes.py`: HTTP and WebSocket endpoints.
- `harness/`: Manager, Auditor, and the round loop.
- `agents/`: one executor per file, all implementing `Executor` from `agents/base.py`.
- `clients/`: wrappers for LFM, LFM-Audio, Nimble and BFL.
- `state/`: contract/report schemas, the append-only report log, and the case workspace.

## Harness invariants

- The Manager never reads the case workspace, only reports and doctor inputs.
- The Auditor is read-only.
- Only de-identified text may leave the device (see `phi.py`).
- `cases/` may contain PHI and must never be committed.

## Adding dependencies

- Python: pin the exact version in `requirements.txt`.
- Frontend: `npm install <pkg>` in `frontend/` and commit the lockfile.
