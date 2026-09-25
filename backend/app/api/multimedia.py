"""Standalone handoff from a verifier; no dependency on transcription or the harness."""
import json
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, TypeAdapter, ValidationError

from backend.app.clients.bfl import BFLClient, BFLError
from backend.app.config import settings
from backend.app.agents.verification import VerificationOutput
from backend.app.state.multimedia import MultimediaRequest, ReferenceImage, VerificationResult, build_payload

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


class FromVerification(BaseModel):
    """The verifier's own output, as produced by VerificationAgent.verify."""

    model_config = ConfigDict(extra="forbid")
    verification_output: VerificationOutput
    original_prompt: str | None = Field(default=None, max_length=8000)  # defaults to the verifier's input
    duration: int = Field(default=10, ge=5, le=20, strict=True)


def from_verification(body: FromVerification) -> MultimediaRequest:
    """Adapt verifier output to the generation request, keeping only the evidence it cited."""
    out = body.verification_output
    if out.decision != "multimedia_generation" or out.handoff is None:
        raise HTTPException(409, f"Verifier routed to {out.decision!r}, not multimedia_generation")
    a, handoff = out.assessment, out.handoff
    cited = [r for r in handoff.results if r.id in set(a.evidence_ids)]
    try:
        return _request_from(body, out, cited)
    except ValidationError as exc:
        raise HTTPException(422, f"Verifier output does not fit a generation request: {exc.errors()[0]['msg']}") from exc


def _request_from(body: FromVerification, out: VerificationOutput, cited: list) -> MultimediaRequest:
    a, handoff = out.assessment, out.handoff
    return MultimediaRequest(
        original_prompt=(body.original_prompt or handoff.original_prompt)[:8000],
        duration=body.duration,
        verification=VerificationResult(
            subject=handoff.transcribed_prompt[:2000],
            context="\n".join(f"- {r.publisher or r.url}: {r.text}" for r in cited)[:20000],
            explanation=a.rationale[:20000],
            description={
                "generation_requirements": a.generation_requirements,
                "assumptions": a.assumptions,
                "missing_evidence": a.missing_evidence,
            },
            images=[
                ReferenceImage(url=m.url, source=r.publisher[:2000], caption=m.description[:4000])
                for r in cited
                for m in r.media
                if m.kind == "image" and m.url.startswith("https://")
            ][:20],
        ),
    )


@router.post("/from-verification/preview")
def preview_from_verification(body: FromVerification) -> dict:
    return preview(from_verification(body))


@router.post("/from-verification", status_code=202)
async def generate_from_verification(body: FromVerification) -> dict:
    return await generate(from_verification(body))


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
