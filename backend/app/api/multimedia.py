"""Standalone handoff from a verifier; no dependency on transcription or the harness."""
import json
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import HttpUrl, TypeAdapter, ValidationError

from backend.app.clients.bfl import BFLClient, BFLError
from backend.app.config import settings
from backend.app.state.multimedia import MultimediaRequest, build_payload

router = APIRouter(prefix="/multimedia", tags=["multimedia"])
TERMINAL = {"Ready", "Error", "Request Moderated", "Content Moderated", "Task not found"}


def job_path(job_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}", job_id):
        raise HTTPException(404, "Generation not found")
    return settings.cases_dir / "multimedia" / f"{job_id}.json"


def save_job(path: Path, job: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(job, indent=2))
    temporary.replace(path)


def public_job(job: dict) -> dict:
    return {k: job.get(k) for k in ("id", "status", "sample_url", "message")}


@router.post("/preview")
def preview(request: MultimediaRequest) -> dict:
    return {"endpoint": "https://api.bfl.ai/v1/flux-3-video", "payload": build_payload(request)}


@router.post("", status_code=202)
async def generate(request: MultimediaRequest) -> dict:
    payload = build_payload(request)
    try:
        submitted = await BFLClient().submit(payload)
    except BFLError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    job_id = uuid.uuid4().hex
    job = {"id": job_id, "provider_id": submitted["id"], "polling_url": submitted["polling_url"],
           "status": "Pending", "request": request.model_dump(mode="json"), "payload": payload}
    save_job(job_path(job_id), job)
    return public_job(job)


@router.get("/{job_id}")
async def get_generation(job_id: str) -> dict:
    path = job_path(job_id)
    if not path.exists():
        raise HTTPException(404, "Generation not found")
    job = json.loads(path.read_text())
    if job["status"] not in TERMINAL:
        try:
            result = await BFLClient().poll(job["polling_url"])
        except BFLError as exc:
            raise HTTPException(exc.status_code, str(exc)) from exc
        status = result.get("status")
        if not isinstance(status, str) or status not in TERMINAL | {"Pending", "Reasoning", "Generating"}:
            raise HTTPException(502, "BFL returned an unknown generation status")
        job["status"] = status
        if status == "Ready":
            media = result.get("result")
            sample = media.get("sample") if isinstance(media, dict) else None
            try:
                parsed = TypeAdapter(HttpUrl).validate_python(sample)
                if parsed.scheme != "https" or parsed.username or parsed.password:
                    raise ValueError("expected HTTPS URL without credentials")
            except (ValidationError, ValueError) as exc:
                raise HTTPException(502, "BFL finished without a valid video URL") from exc
            job["sample_url"] = str(parsed)
        elif status in TERMINAL:
            job["message"] = f"Generation ended: {status}."
        # Another request may have completed while this one awaited BFL. Do not
        # replace its terminal result with a stale provider response.
        latest = json.loads(path.read_text())
        if latest["status"] in TERMINAL:
            return public_job(latest)
        save_job(path, job)
    return public_job(job)
