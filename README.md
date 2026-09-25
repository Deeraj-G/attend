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

Give Docker at least 10GB of memory: `lfm-audio` runs in float32 (~7GB) because
its bfloat16 CPU kernels crash with SIGILL on Apple silicon.

| Service | Port | Notes |
|---|---|---|
| frontend | 5173 | Vite dev server |
| backend | 8000 | FastAPI with autoreload |
| lfm | 8081 | llama.cpp server, OpenAI-compatible API |
| lfm-audio | 8090 | `POST /transcribe`, `POST /synthesize` |

`backend/` and `frontend/` are bind-mounted, so edits on the host reload live.
The backend container gets `LFM_BASE_URL` and `LFM_AUDIO_BASE_URL`, so
`LFMClient`/`LFMAudioClient` call the model containers over HTTP and the image
installs only `requirements-core.txt` (no torch). Without those variables, as on
the host venv, the clients load the models in-process.

## Adding dependencies

- Python: `pip install <pkg>`, then pin the exact version in `requirements.txt`.
- Frontend: `npm install <pkg>` in `frontend/`, and commit `package-lock.json`.

## Verifier → FLUX 3 multimedia

Set `BFL_API_KEY` in the backend `.env`, then send the original prompt and
verifier JSON directly to the API at `http://localhost:8000`. This uses the
[FLUX 3 video API](https://docs.bfl.ml/flux_3/flux3_video), producing 5–20 second
videos. No frontend changes are required.

Example request body (replace the illustrative image URL with a real source):

```http
POST /multimedia
Content-Type: application/json

{
  "original_prompt": "Compare a healthy eye and an eye with retinal vein occlusion side by side.",
  "verification": {
    "subject": "Retinal vein occlusion",
    "context": "Background supplied by the verifier",
    "explanation": "Visual explanation supplied by the verifier",
    "description": {"types": ["CRVO", "BRVO"]},
    "images": [{"url": "https://example.com/eye.png", "source": "Source name", "caption": "Image explanation"}]
  },
  "duration": 10,
  "resolution": "hd",
  "aspect_ratio": "16:9",
  "generate_audio": false,
  "opening_image_index": null
}
```

- `POST /multimedia/preview` accepts the same body and returns the exact BFL payload
  without submitting a paid generation. `context` is required; `explanation`,
  `description`, `subject`, and `images` are optional.
- `POST /multimedia` returns HTTP 202 with a local job `id` and `status`.
- `GET /multimedia/{id}` polls BFL and returns `status`, `sample_url`, and `message`.
- All image URLs and captions are preserved in the prompt as textual background.
  They are **not** automatically fetched or visually understood in text-to-video mode.
  Set `opening_image_index` to a zero-based image index for image-to-video; that image
  becomes the exact opening frame. Multiple unrelated clinical images should not
  be passed as sequential keyframes for a side-by-side comparison.
- Jobs and their original requests are stored under `CASES_DIR/multimedia/`.
  Keep the returned job ID and poll `GET /multimedia/{id}` to retrieve the result,
  including after a backend restart. The caller controls the polling interval and
  timeout. Submission is never automatically retried because it may incur another charge.
- The signed video URL is temporary. Save the clip promptly; videos are not archived
  by this interface. A new generation has not itself been medically verified.

This standalone handoff expects already de-identified verifier content. It does not
connect raw transcripts or implement the unfinished PHI scrubber/harness. The local
API has no authentication and is intended for localhost development.

Backend contract and mocked provider tests (no BFL key or paid requests required):

```bash
python -m unittest discover -s backend/tests -p 'test_multimedia.py' -v
```
