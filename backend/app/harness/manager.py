"""ManagerAgent: a rule-based scheduler over the report log (ADR 0004).

Reads audit reports and doctor inputs only, never the workspace. Holds no state of its own:
every round rebuilds the task state from the logs and emits one decision.
"""

from typing import Literal

from pydantic import BaseModel

from backend.app.harness.contracts import build_contract
from backend.app.harness.state import SubtaskState, TaskState, build_state, max_attempts
from backend.app.state.schemas import Contract, DoctorInput, Report

SUSPECT_BOUNDARY = "write only your declared outputs; a previous attempt modified other files"


class AskDoctor(BaseModel):
    """Ask route: the loop pauses until a doctor input arrives."""

    kind: Literal["recording", "conflict", "violation", "retries_exhausted", "approval"]
    question: str
    subtask: str | None = None


class Done(BaseModel):
    pass


type ManagerDecision = Contract | AskDoctor | Done


class ManagerAgent:
    def next_step(self, reports: list[Report], inputs: list[DoctorInput], round_no: int) -> ManagerDecision:
        state = build_state(reports, inputs)
        if state.recording is None:
            return AskDoctor(kind="recording", question="Record a description of the procedure.")

        if violation := _unresolved_violation(state):
            return AskDoctor(
                kind="violation",
                question=f"PHI was found in an outbound request from {violation.subtask}. "
                "Review the case, then answer to resume.",
                subtask=violation.subtask,
            )

        for subtask in state.subtasks.values():
            if not subtask.fresh and subtask.stale_since is not None:
                return _decide(state, subtask, round_no)

        assemble = state.subtasks.get("assemble")
        approved_at = [i.created_at for i in state.inputs if i.kind == "approval"]
        if assemble and assemble.fresh_report and any(t > assemble.fresh_report.created_at for t in approved_at):
            return Done()
        return AskDoctor(kind="approval", question="Review final.mp4 and approve it or request an edit.")


def _unresolved_violation(state: TaskState) -> Report | None:
    """A violation is resolved by a doctor answer targeting its subtask that is newer than it."""
    assert state.recording is not None
    latest: dict[str, Report] = {}
    for r in state.all_reports:
        if r.created_at > state.recording.created_at:
            latest[r.subtask] = r
    for r in latest.values():
        answers = state.inputs_for(r.subtask, "answer")
        if r.integrity == "violation" and not any(a.created_at > r.created_at for a in answers):
            return r
    return None


def _decide(state: TaskState, s: SubtaskState, round_no: int) -> ManagerDecision:
    """ADR 0004, "When a report comes back"."""
    latest = s.latest
    if latest is None:
        return _contract(state, s, round_no)

    # A doctor answer newer than the latest report unblocks it and allows one more attempt.
    answered = any(a.created_at > latest.created_at for a in state.inputs_for(s.key, "answer"))
    can_retry = answered or s.attempts < max_attempts(s.key)

    if latest.integrity == "violation":  # resolved, or the global check would have stopped us
        return _contract(state, s, round_no, retry_of=latest)

    if latest.integrity == "suspect":
        if can_retry:
            return _contract(state, s, round_no, retry_of=latest, extra_boundaries=[SUSPECT_BOUNDARY])
        return _retries_exhausted(s)

    if latest.status == "blocked":
        if answered:
            return _contract(state, s, round_no, retry_of=latest)
        question = latest.state_update.data.get("question") or "; ".join(latest.state_update.gaps)
        return AskDoctor(kind="conflict", question=question or f"{s.key} is blocked.", subtask=s.key)

    # incomplete + clean (complete + clean would already be fresh)
    if can_retry:
        gaps = [f"Resolve: {g}" for g in latest.state_update.gaps]
        return _contract(state, s, round_no, retry_of=latest, extra_acceptance=gaps)
    return _retries_exhausted(s)


def _retries_exhausted(s: SubtaskState) -> AskDoctor:
    return AskDoctor(
        kind="retries_exhausted",
        question=f"{s.key} failed {s.attempts} attempts. Answer with guidance to retry.",
        subtask=s.key,
    )


def _contract(
    state: TaskState,
    s: SubtaskState,
    round_no: int,
    retry_of: Report | None = None,
    extra_acceptance: list[str] | None = None,
    extra_boundaries: list[str] | None = None,
) -> Contract:
    boundaries = list(extra_boundaries or [])
    # Doctor feedback carries forward across regenerations of the same subtask.
    boundaries += [f"Doctor edit: {i.text}" for i in state.inputs_for(s.key, "edit") if i.text]
    boundaries += [f"Doctor answered: {i.text}" for i in state.inputs_for(s.key, "answer") if i.text]
    if s.key == "storyboard" and (gaps := state.subtasks["research"].accepted_gaps):
        boundaries.append(f"Research gaps (do not invent content): {', '.join(gaps)}")

    related = [d.fresh_report.id for d in (state.subtasks[k] for k in s.deps) if d.fresh_report]
    if retry_of:
        related.append(retry_of.id)

    return build_contract(
        s.key,
        attempt=s.attempts + 1,
        round_no=round_no,
        related_reports=related,
        extra_acceptance=extra_acceptance,
        extra_boundaries=boundaries,
    )
