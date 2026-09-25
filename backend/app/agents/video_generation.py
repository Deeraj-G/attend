"""One patient-education video per case via Black Forest Labs (Juan's /multimedia payload)."""

import asyncio
import json

from backend.app.clients.bfl import BFLClient, BFLError
from backend.app.phi import contains_phi
from backend.app.state.multimedia import MultimediaRequest, ReferenceImage, VerificationResult, build_payload
from backend.app.state.reports import ReportLog
from backend.app.state.schemas import Contract, ExecutorOutput
from backend.app.state.workspace import Workspace

VIDEO = "video.json"
TERMINAL = {"Ready", "Error", "Request Moderated", "Content Moderated", "Task not found"}
POLL_SECONDS = 5
MAX_POLLS = 120  # ~10 minutes


def build_request(
    contract: Contract, brief: dict, sources: dict, media: dict, verdict: dict | None = None
) -> MultimediaRequest:
    """verdict is the research report's data: the verifier's cited evidence and requirements."""
    verdict = verdict or {}
    steps = "; ".join(brief.get("steps", []))
    prompt = f"Explain what happens during a {brief['procedure']} for a nervous patient. Steps: {steps}"
    # Doctor edits and answers arrive as contract boundaries; pass them on as production notes.
    notes = [b for b in contract.boundaries if b.startswith(("Doctor edit:", "Doctor answered:"))]
    if notes:
        prompt += "\nDoctor notes: " + " ".join(notes)
    # Prefer the sources the verifier cited; fall back to trusted ones if it cited none.
    cited = set(verdict.get("evidence_urls", []))
    chosen = [s for s in sources.get("sources", []) if s["url"] in cited]
    chosen = chosen or [s for s in sources.get("sources", []) if s.get("trusted")]
    chosen = chosen[:6]
    return MultimediaRequest(
        original_prompt=prompt[:8000],
        verification=VerificationResult(
            subject=brief["procedure"],
            context="\n".join(f"- {s['title']}: {s['snippet']}" for s in chosen)[:20000] or brief["procedure"],
            explanation="; ".join(brief.get("patient_concerns", []))[:20000],
            description={
                k: verdict[k]
                for k in ("generation_requirements", "assumptions", "missing_evidence")
                if verdict.get(k)
            },
            images=[
                ReferenceImage(url=i["url"], source=i.get("domain", ""), caption=i.get("title", ""))
                for i in media.get("images", [])[:3]
                if str(i.get("url", "")).startswith("https://")
            ],
        ),
    )


class VideoGenerationAgent:
    name = "video_generation"

    def __init__(self, client: BFLClient | None = None) -> None:
        self.client = client or BFLClient()

    async def run(self, contract: Contract, workspace: Workspace) -> ExecutorOutput:
        def load(name: str) -> dict:
            path = workspace.path(name)
            return json.loads(path.read_text()) if path.exists() else {}

        brief = load(Workspace.BRIEF)
        if not brief.get("procedure"):
            return ExecutorOutput(contract_id=contract.id, summary=f"missing input: {Workspace.BRIEF}")
        verdict = _research_verdict(workspace, contract.related_reports)
        request = build_request(contract, brief, load(Workspace.SOURCES), load(Workspace.MEDIA_REFS), verdict)
        payload = build_payload(request)
        if contains_phi(payload["prompt"]):
            return ExecutorOutput(contract_id=contract.id, summary="prompt blocked for PHI", data={"phi_blocked": 1})

        job: dict = {"status": "Error", "sample_url": None, "message": None}
        try:
            submitted = await self.client.submit(payload)
            for _ in range(MAX_POLLS):
                result = await self.client.poll(submitted["polling_url"])
                job["status"] = result.get("status", "Error")
                if job["status"] in TERMINAL:
                    break
                await asyncio.sleep(POLL_SECONDS)
            sample = (result.get("result") or {}).get("sample") if isinstance(result.get("result"), dict) else None
            if job["status"] == "Ready" and isinstance(sample, str) and sample.startswith("https://"):
                job["sample_url"] = sample
        except BFLError as e:
            job["message"] = str(e)

        workspace.path(VIDEO).write_text(json.dumps(job, indent=2))
        workspace.record_provenance(VIDEO, self.name)
        return ExecutorOutput(
            contract_id=contract.id,
            artifacts=[VIDEO],
            summary=f"BFL video: {job['status']}" + (f" ({job['message']})" if job["message"] else ""),
            data={"status": job["status"], "ready": int(bool(job["sample_url"])), "phi_blocked": 0},
        )


def _research_verdict(workspace: Workspace, report_ids: list[str]) -> dict:
    """The verifier's findings, from the research report the Manager passed as related."""
    wanted = set(report_ids)
    for report in reversed(ReportLog(workspace.dir).read_all()):
        if report.id in wanted and report.subtask == "research":
            return report.state_update.data
    return {}
