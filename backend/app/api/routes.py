import re
import uuid

import json

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile, WebSocket
from pydantic import BaseModel

from backend.app.agents.transcription import TranscriptionAgent, transcription_contract
from backend.app.agents.web_search import WebSearchAgent, research_contract
from backend.app.harness.loop import run_case
from backend.app.recorder import RecordingError, save_upload
from backend.app.state.inputs import InputLog
from backend.app.state.reports import ReportLog
from backend.app.state.schemas import Case, DoctorInput, ExecutorOutput, Report
from backend.app.state.workspace import Workspace

router = APIRouter()

_CASE_ID = re.compile(r"^[0-9a-f]{12}$")


def _workspace(case_id: str) -> Workspace:
    # Validate before touching the filesystem: case_id becomes a directory name.
    if not _CASE_ID.match(case_id):
        raise HTTPException(404, "case not found")
    workspace = Workspace(case_id)
    if not workspace.exists():
        raise HTTPException(404, "case not found")
    return workspace


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/cases")
def create_case() -> Case:
    case = Case(id=uuid.uuid4().hex[:12])
    Workspace(case.id).save_case(case)
    return case


@router.get("/cases/{case_id}")
def get_case(case_id: str) -> Case:
    return _workspace(case_id).load_case()


DECISION = "decision.json"


async def _run(case_id: str) -> None:
    """Run the harness until it needs the doctor; the decision is what the UI shows next."""
    workspace = Workspace(case_id)
    try:
        decision = await run_case(case_id)
        state = {"state": "done" if decision.__class__.__name__ == "Done" else "waiting", **decision.model_dump()}
    except Exception as e:  # surface failures to the UI instead of losing them in a background task
        state = {"state": "error", "error": f"{type(e).__name__}: {e}"}
    workspace.path(DECISION).write_text(json.dumps(state, indent=2))


def _record(case_id: str, background: BackgroundTasks, **fields) -> dict[str, str]:
    workspace = _workspace(case_id)
    log = InputLog(workspace.dir)
    log.append(DoctorInput(id=f"i{len(log.read_all()) + 1}", **fields))
    workspace.path(DECISION).write_text(json.dumps({"state": "running"}))
    background.add_task(_run, case_id)
    return {"state": "running"}


@router.post("/cases/{case_id}/audio")
async def upload_audio(case_id: str, file: UploadFile, background: BackgroundTasks, run: bool = False) -> dict:
    """Step 0: the doctor's recording. Stays on device. run=true also starts the harness."""
    workspace = _workspace(case_id)
    try:
        duration = save_upload(workspace, await file.read())
    except RecordingError as e:
        raise HTTPException(422, str(e)) from e
    if run:
        _record(case_id, background, kind="recording")
    return {"path": Workspace.AUDIO, "duration_s": round(duration, 2)}


@router.post("/cases/{case_id}/run")
def start(case_id: str, background: BackgroundTasks) -> dict[str, str]:
    """Start the Manage-Execute-Audit harness on the uploaded recording."""
    if not _workspace(case_id).path(Workspace.AUDIO).exists():
        raise HTTPException(409, "no recording uploaded yet")
    return _record(case_id, background, kind="recording")


class DoctorText(BaseModel):
    text: str
    target: str | None = None


@router.get("/cases/{case_id}/status")
def status(case_id: str) -> dict:
    """What the harness is doing: running, waiting (with the question for the doctor), done or error."""
    path = _workspace(case_id).path(DECISION)
    return json.loads(path.read_text()) if path.exists() else {"state": "idle"}


@router.post("/cases/{case_id}/answer")
def answer(case_id: str, body: DoctorText, background: BackgroundTasks) -> dict[str, str]:
    return _record(case_id, background, kind="answer", target=body.target, text=body.text)


@router.get("/cases/{case_id}/video")
def video(case_id: str) -> dict:
    path = _workspace(case_id).path("video.json")
    if not path.exists():
        raise HTTPException(404, "no video yet")
    return json.loads(path.read_text())


@router.post("/cases/{case_id}/transcribe")
async def transcribe(case_id: str) -> ExecutorOutput:
    """Step 1, run directly until the Manager issues c1 contracts itself."""
    workspace = _workspace(case_id)
    if not workspace.path(Workspace.AUDIO).exists():
        raise HTTPException(409, "no recording uploaded yet")
    return await TranscriptionAgent().run(transcription_contract(), workspace)


@router.get("/cases/{case_id}/transcript")
def get_transcript(case_id: str) -> dict[str, str]:
    path = _workspace(case_id).path(Workspace.TRANSCRIPT)
    if not path.exists():
        raise HTTPException(404, "not transcribed yet")
    return {"text": path.read_text().strip()}


@router.post("/cases/{case_id}/research")
async def research(case_id: str) -> ExecutorOutput:
    """Step 3, run directly until the Manager issues c3 contracts itself."""
    workspace = _workspace(case_id)
    if not workspace.path(Workspace.BRIEF).exists():
        raise HTTPException(409, "no de-identified brief yet (step 2)")
    return await WebSearchAgent().run(research_contract(), workspace)


@router.get("/cases/{case_id}/reports")
def list_reports(case_id: str) -> list[Report]:
    return ReportLog(_workspace(case_id).dir).read_all()


@router.post("/cases/{case_id}/edit")
def request_edit(case_id: str, body: DoctorText, background: BackgroundTasks) -> dict[str, str]:
    """Doctor's edit request; regenerates the target (default: the video)."""
    return _record(case_id, background, kind="edit", target=body.target or "video", text=body.text)


@router.post("/cases/{case_id}/approve")
def approve(case_id: str, background: BackgroundTasks) -> dict[str, str]:
    return _record(case_id, background, kind="approval")


@router.websocket("/cases/{case_id}/trace")
async def trace(websocket: WebSocket, case_id: str) -> None:
    """Streams harness rounds (contracts, reports) to the trace panel."""
    await websocket.accept()
    raise NotImplementedError
