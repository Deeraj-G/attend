"""Task state rebuilt from reports.jsonl + inputs.jsonl each round (ADR 0004).

A subtask is *fresh* when its latest report since it last became stale is complete and not
suspect. A violation report counts: the Auditor has already discarded the items with PHI.
It becomes stale when a dependency becomes fresh again, or when the doctor edits it.
"""

from dataclasses import dataclass, field
from datetime import datetime

from backend.app.config import settings
from backend.app.state.schemas import DoctorInput, Report

FIXED_ORDER = ["transcribe", "deidentify", "research", "storyboard", "narration"]


@dataclass
class SubtaskState:
    key: str
    deps: list[str]
    fresh: bool = False
    fresh_report: Report | None = None  # the report that made it fresh
    stale_since: datetime | None = None
    reports: list[Report] = field(default_factory=list)  # since stale_since, oldest first
    accepted_gaps: list[str] = field(default_factory=list)  # research that ran out of attempts

    @property
    def latest(self) -> Report | None:
        return self.reports[-1] if self.reports else None

    @property
    def attempts(self) -> int:
        return len(self.reports)


@dataclass
class TaskState:
    recording: DoctorInput | None
    inputs: list[DoctorInput]  # since the latest recording
    subtasks: dict[str, SubtaskState]  # topological order
    all_reports: list[Report]

    def inputs_for(self, subtask: str, kind: str) -> list[DoctorInput]:
        return [i for i in self.inputs if i.kind == kind and i.target == subtask]


def max_attempts(subtask: str) -> int:
    return settings.max_research_iterations if subtask == "research" else settings.max_attempts


def build_state(reports: list[Report], inputs: list[DoctorInput]) -> TaskState:
    inputs = sorted(inputs, key=lambda i: i.created_at)
    recordings = [i for i in inputs if i.kind == "recording"]
    recording = recordings[-1] if recordings else None
    if recording:
        inputs = [i for i in inputs if i.created_at >= recording.created_at]
    reports = sorted(reports, key=lambda r: r.created_at)

    state = TaskState(recording=recording, inputs=inputs, subtasks={}, all_reports=reports)
    if recording is None:
        return state

    by_subtask: dict[str, list[Report]] = {}
    for r in reports:
        by_subtask.setdefault(r.subtask, []).append(r)

    def add(key: str, deps: list[str]) -> SubtaskState:
        s = SubtaskState(key=key, deps=deps)
        state.subtasks[key] = s
        dep_states = [state.subtasks[d] for d in deps]
        if not all(d.fresh for d in dep_states):
            return s

        # Stale since the newest of: dep results, edits aimed at this subtask, the recording.
        times = [recording.created_at]
        times += [d.fresh_report.created_at for d in dep_states if d.fresh_report]
        times += [i.created_at for i in state.inputs_for(key, "edit")]
        s.stale_since = max(times)
        s.reports = [r for r in by_subtask.get(key, []) if r.created_at > s.stale_since]

        # violation: the Auditor discarded the offending items; what is left is judged on status.
        latest = s.latest
        if latest and latest.integrity in ("clean", "violation"):
            if latest.status == "complete":
                s.fresh, s.fresh_report = True, latest
            elif key == "research" and latest.status == "incomplete" and s.attempts >= max_attempts(key):
                s.fresh, s.fresh_report = True, latest
                s.accepted_gaps = list(latest.state_update.gaps)
        return s

    for i, key in enumerate(FIXED_ORDER):
        add(key, [FIXED_ORDER[i - 1]] if i else [])

    storyboard = state.subtasks["storyboard"]
    if storyboard.fresh and storyboard.fresh_report:
        scene_count = int(storyboard.fresh_report.state_update.data.get("scene_count", 0))
        scenes = [f"scene:{n}" for n in range(1, scene_count + 1)]
        for scene in scenes:
            add(scene, ["storyboard"])
        add("assemble", ["narration", *scenes])

    return state
