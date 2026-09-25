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

The first transcription downloads LFM2.5-Audio-1.5B (~7 GB) from Hugging Face into
`~/.cache/huggingface`. Set `LFM_AUDIO_MODEL_PATH` to use a local copy instead.

## Record and transcribe (steps 0-1)

In the browser: open http://localhost:5173, record (or import a file), then **Transcribe**.

From the terminal (no UI or server needed):

```bash
python -m backend.scripts.record --transcribe          # record from the mic; Enter stops
python -m backend.scripts.record --file a.wav --transcribe
```

Each run creates `cases/<case_id>/` with `audio/recording.wav` (mono 16-bit WAV),
`transcript.txt` (input to de-identification), `transcript.json` (per-segment timings and
checks) and `provenance.json`. `cases/` is gitignored because it may contain PHI.

## Research (step 3)

Needs `NIMBLE_API_KEY` in `.env`. Reads the de-identified `brief.json` (step 2) and makes at
most 3 Nimble calls (`NIMBLE_MAX_CALLS_PER_RUN`): text from trusted medical sites, Google
Images, and YouTube/Vimeo videos. Every query is checked for PHI before it is sent.

```bash
python -m backend.scripts.research --procedure "colonoscopy"   # new case with a stand-in brief
python -m backend.scripts.research --case <case_id>            # existing case with brief.json
```

Or `POST /cases/<case_id>/research`. Writes `sources.json` (text sources, each flagged
`trusted`) and `media_refs.json` (image and video references for prompt writing only; never
put them in the output video).

## Adding dependencies

- Python: `pip install <pkg>`, then pin the exact version in `requirements.txt`.
- Frontend: `npm install <pkg>` in `frontend/`, and commit `package-lock.json`.
