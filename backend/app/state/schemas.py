from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class ExecutorName(StrEnum):
    TRANSCRIPTION = "transcription"
    DEIDENTIFY = "deidentify"
    WEB_SEARCH = "web_search"
    VERIFICATION = "verification"
    SCRIPT = "script"
    VIDEO_GENERATION = "video_generation"
    ASSEMBLY = "assembly"


class Contract(BaseModel):
    """Subtask contract c_i emitted by the Manager."""

    id: str
    subtask: str  # e.g. "research", "scene:3"
    attempt: int = 1
    executor: ExecutorName
    goal: str
    acceptance_criteria: list[str]
    boundaries: list[str] = []
    related_reports: list[str] = []


class ExecutorOutput(BaseModel):
    """Output o_i from an executor. Its trajectory is discarded."""

    contract_id: str
    artifacts: list[str] = []  # workspace-relative paths written
    summary: str = ""
    data: dict[str, Any] = {}  # numbers the Auditor can check; never artifact content (PHI)


class StateUpdate(BaseModel):
    facts: list[str] = []
    evidence: list[str] = []
    gaps: list[str] = []
    data: dict[str, Any] = {}  # structured values for the Manager: scene_count, question, ...


class Report(BaseModel):
    """Audit report V_i. The only thing the Manager reads."""

    id: str
    contract_id: str
    subtask: str  # copied from the contract by the Auditor
    status: Literal["complete", "incomplete", "blocked"]
    integrity: Literal["clean", "suspect", "violation"]
    state_update: StateUpdate = StateUpdate()
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DoctorInput(BaseModel):
    """Doctor input from inputs.jsonl: the recording, answers, edits and approval."""

    id: str
    kind: Literal["recording", "answer", "edit", "approval"]
    target: str | None = None  # subtask key for answers and edits
    text: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Artifact(BaseModel):
    """A workspace file and the executor that wrote it."""

    path: str
    written_by: str
    sha256: str


class Case(BaseModel):
    id: str
    procedure: str | None = None
    approved: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
