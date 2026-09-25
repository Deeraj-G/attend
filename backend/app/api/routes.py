from fastapi import APIRouter, UploadFile, WebSocket

from backend.app.state.reports import ReportLog
from backend.app.state.schemas import Case, Report
from backend.app.state.workspace import Workspace

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/cases")
def create_case() -> Case:
    raise NotImplementedError


@router.post("/cases/{case_id}/audio")
async def upload_audio(case_id: str, file: UploadFile) -> dict[str, str]:
    raise NotImplementedError


@router.get("/cases/{case_id}/reports")
def list_reports(case_id: str) -> list[Report]:
    return ReportLog(Workspace(case_id).dir).read_all()


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
