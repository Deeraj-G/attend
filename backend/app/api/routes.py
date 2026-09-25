import re
import uuid

from fastapi import APIRouter, HTTPException, UploadFile, WebSocket

from backend.app.agents.transcription import TranscriptionAgent, transcription_contract
from backend.app.agents.web_search import WebSearchAgent, research_contract
from backend.app.recorder import RecordingError, save_upload
from backend.app.state.reports import ReportLog
from backend.app.state.schemas import Case, ExecutorOutput, Report
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


@router.post("/cases/{case_id}/audio")
async def upload_audio(case_id: str, file: UploadFile) -> dict[str, str | float]:
    """Step 0: the doctor's recording. Stays on device."""
    workspace = _workspace(case_id)
    try:
        duration = save_upload(workspace, await file.read())
    except RecordingError as e:
        raise HTTPException(422, str(e)) from e
    return {"path": Workspace.AUDIO, "duration_s": round(duration, 2)}


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
async def request_edit(case_id: str, file: UploadFile) -> dict[str, str]:
    """Doctor's voice edit request, transcribed on device."""
    raise NotImplementedError


@router.post("/cases/{case_id}/approve")
def approve(case_id: str) -> Case:
    raise NotImplementedError


@router.websocket("/cases/{case_id}/trace")
async def trace(websocket: WebSocket, case_id: str) -> None:
    """Streams harness rounds (contracts, reports) to the trace panel."""
    await websocket.accept()
    raise NotImplementedError
