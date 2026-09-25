"""ManagerAgent decision tests (ADR 0004). One test per outcome row, plus end-to-end scenarios."""

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from itertools import count

import pytest

from backend.app.harness.manager import SUSPECT_BOUNDARY, AskDoctor, Done, ManagerAgent
from backend.app.state.inputs import InputLog
from backend.app.state.schemas import Contract, DoctorInput, Report, StateUpdate

T0 = datetime(2026, 9, 25, tzinfo=timezone.utc)


class Case:
    """Holds both logs and a fake clock; plays the loop with scripted audit outcomes."""

    def __init__(self) -> None:
        self.reports: list[Report] = []
        self.inputs: list[DoctorInput] = []
        self._tick = count(1)
        self.round = 0
        self.manager = ManagerAgent()

    def now(self) -> datetime:
        return T0 + timedelta(seconds=next(self._tick))

    def doctor(self, kind: str, target: str | None = None, text: str | None = None) -> None:
        self.inputs.append(
            DoctorInput(id=f"i{len(self.inputs) + 1}", kind=kind, target=target, text=text, created_at=self.now())
        )

    def step(self):
        self.round += 1
        return self.manager.next_step(self.reports, self.inputs, self.round)

    def audit(
        self,
        contract: Contract,
        status: str = "complete",
        integrity: str = "clean",
        gaps: list[str] | None = None,
        data: dict | None = None,
    ) -> Report:
        if data is None and contract.subtask == "storyboard" and status == "complete":
            data = {"scene_count": 3}
        report = Report(
            id=f"v{len(self.reports) + 1}",
            contract_id=contract.id,
            subtask=contract.subtask,
            status=status,
            integrity=integrity,
            state_update=StateUpdate(gaps=gaps or [], data=data or {}),
            created_at=self.now(),
        )
        self.reports.append(report)
        return report

    def run(self, outcome: Callable[[Contract], dict] | None = None, max_rounds: int = 50):
        """Complete every contract (or apply `outcome`) until the Manager asks or finishes.

        Returns the stopping decision and the subtasks issued, in order.
        """
        issued = []
        for _ in range(max_rounds):
            decision = self.step()
            if not isinstance(decision, Contract):
                return decision, issued
            issued.append(decision.subtask)
            self.audit(decision, **(outcome(decision) if outcome else {}))
        raise AssertionError("manager did not stop")


PIPELINE = ["transcribe", "deidentify", "research", "storyboard", "narration", "scene:1", "scene:2", "scene:3", "assemble"]


@pytest.fixture
def case() -> Case:
    c = Case()
    c.doctor("recording")
    return c


# --- start and happy path -------------------------------------------------------------------


def test_no_recording_asks_for_one():
    decision = Case().step()
    assert isinstance(decision, AskDoctor) and decision.kind == "recording"


def test_first_contract_is_transcribe(case):
    c = case.step()
    assert isinstance(c, Contract)
    assert (c.subtask, c.attempt, c.id) == ("transcribe", 1, "c01-transcribe-a1")
    assert c.executor == "transcription"


def test_happy_path_runs_every_subtask_in_order_then_asks_for_approval(case):
    decision, issued = case.run()
    assert issued == PIPELINE
    assert isinstance(decision, AskDoctor) and decision.kind == "approval"


def test_approval_finishes(case):
    case.run()
    case.doctor("approval")
    assert isinstance(case.step(), Done)


def test_related_reports_are_fresh_dependency_reports(case):
    case.run()
    reports = {r.subtask: r.id for r in case.reports}
    case.doctor("edit", target="narration", text="slower")
    narration = case.step()
    assert narration.related_reports == [reports["storyboard"]]
    case.audit(narration)
    assemble = case.step()
    assert assemble.subtask == "assemble"
    assert assemble.related_reports == [case.reports[-1].id, reports["scene:1"], reports["scene:2"], reports["scene:3"]]


def test_scene_contract_is_formatted_for_its_scene(case):
    for _ in range(5):  # transcribe .. narration
        case.audit(case.step())
    scene = case.step()
    assert (scene.subtask, scene.executor, scene.id) == ("scene:1", "video_generation", "c06-scene-1-a1")
    assert scene.goal == "Generate the clip for scene 1."
    assert "write only scenes/scene_1.mp4" in scene.boundaries


# --- report outcome table -------------------------------------------------------------------


def test_incomplete_retries_with_gaps_as_acceptance(case):
    first = case.step()
    case.audit(first, status="incomplete", gaps=["segment 2 empty"])
    retry = case.step()
    assert (retry.subtask, retry.attempt) == ("transcribe", 2)
    assert "Resolve: segment 2 empty" in retry.acceptance_criteria
    assert case.reports[-1].id in retry.related_reports


def test_incomplete_at_cap_asks_doctor_and_answer_allows_retry(case):
    for _ in range(2):
        case.audit(case.step(), status="incomplete", gaps=["x"])
    decision = case.step()
    assert isinstance(decision, AskDoctor)
    assert (decision.kind, decision.subtask) == ("retries_exhausted", "transcribe")

    case.doctor("answer", target="transcribe", text="speak slower is fine")
    retry = case.step()
    assert (retry.subtask, retry.attempt) == ("transcribe", 3)
    assert "Doctor answered: speak slower is fine" in retry.boundaries


def test_research_at_cap_proceeds_with_gaps_carried_to_storyboard(case):
    def outcome(c: Contract) -> dict:
        return {"status": "incomplete", "gaps": ["recovery timeline"]} if c.subtask == "research" else {}

    for _ in range(2):
        case.audit(case.step())  # transcribe, deidentify
    for attempt in range(1, 4):
        research = case.step()
        assert (research.subtask, research.attempt) == ("research", attempt)
        case.audit(research, **outcome(research))
    storyboard = case.step()
    assert storyboard.subtask == "storyboard"
    assert "Research gaps (do not invent content): recovery timeline" in storyboard.boundaries


def test_blocked_asks_conflict_question(case):
    case.audit(case.step(), status="blocked", data={"question": "Same-day or 2-4 h recovery?"})
    decision = case.step()
    assert isinstance(decision, AskDoctor)
    assert (decision.kind, decision.question, decision.subtask) == (
        "conflict",
        "Same-day or 2-4 h recovery?",
        "transcribe",
    )


def test_blocked_falls_back_to_gaps_for_question(case):
    case.audit(case.step(), status="blocked", gaps=["dosage unclear"])
    assert case.step().question == "dosage unclear"


def test_blocked_with_answer_retries_with_answer_boundary(case):
    case.audit(case.step(), status="blocked", data={"question": "?"})
    case.doctor("answer", target="transcribe", text="same-day")
    retry = case.step()
    assert (retry.subtask, retry.attempt) == ("transcribe", 2)
    assert "Doctor answered: same-day" in retry.boundaries


def test_answer_for_another_subtask_does_not_unblock(case):
    case.audit(case.step(), status="blocked", data={"question": "?"})
    case.doctor("answer", target="research", text="unrelated")
    assert isinstance(case.step(), AskDoctor)


def test_suspect_retries_with_tightened_boundary(case):
    case.audit(case.step(), integrity="suspect")
    retry = case.step()
    assert retry.attempt == 2 and SUSPECT_BOUNDARY in retry.boundaries


def test_suspect_at_cap_asks_doctor(case):
    for _ in range(2):
        case.audit(case.step(), integrity="suspect")
    decision = case.step()
    assert isinstance(decision, AskDoctor) and decision.kind == "retries_exhausted"


def test_violation_complete_discards_and_continues(case):
    for _ in range(2):  # transcribe, deidentify
        case.audit(case.step())
    research = case.step()
    case.audit(research, integrity="violation", data={"discarded": ["sources[2]"]})
    nxt = case.step()
    assert isinstance(nxt, Contract) and nxt.subtask == "storyboard"


def test_violation_incomplete_retries_without_discarded_items(case):
    for _ in range(2):
        case.audit(case.step())
    research = case.step()
    case.audit(research, status="incomplete", integrity="violation", gaps=["recovery"], data={"discarded": ["sources[2]"]})
    retry = case.step()
    assert (retry.subtask, retry.attempt) == ("research", 2)
    assert "Discarded for PHI, do not reuse: sources[2]" in retry.boundaries
    assert "Resolve: recovery" in retry.acceptance_criteria


def test_discarded_items_accumulate_across_attempts(case):
    for _ in range(2):
        case.audit(case.step())
    for ref in ("sources[2]", "media_refs[0]"):
        case.audit(case.step(), status="incomplete", integrity="violation", data={"discarded": [ref]})
    retry = case.step()
    assert "Discarded for PHI, do not reuse: sources[2], media_refs[0]" in retry.boundaries


def test_violation_does_not_block_other_work(case):
    for _ in range(5):  # transcribe .. narration
        case.audit(case.step())
    case.audit(case.step(), integrity="violation", data={"discarded": ["prompt"]})  # scene:1 complete
    nxt = case.step()
    assert isinstance(nxt, Contract) and nxt.subtask == "scene:2"


def test_violation_never_asks_the_doctor(case):
    def outcome(c: Contract) -> dict:
        return {"integrity": "violation", "data": {"discarded": ["x"]}} if c.subtask == "research" else {}

    decision, issued = case.run(outcome)
    assert issued == PIPELINE
    assert decision.kind == "approval"


# --- doctor inputs: edits, re-recording, approval freshness ---------------------------------


def test_edit_regenerates_only_target_and_assemble(case):
    case.run()
    case.doctor("edit", target="scene:2", text="too clinical")
    decision, issued = case.run()
    assert issued == ["scene:2", "assemble"]
    assert isinstance(decision, AskDoctor) and decision.kind == "approval"


def test_edit_text_becomes_boundary_and_persists(case):
    case.run()
    case.doctor("edit", target="scene:2", text="too clinical")
    first = case.step()
    assert "Doctor edit: too clinical" in first.boundaries
    case.audit(first)
    case.run()
    case.doctor("edit", target="scene:2", text="brighter colours")
    second = case.step()
    assert second.attempt == 1
    assert {"Doctor edit: too clinical", "Doctor edit: brighter colours"} <= set(second.boundaries)


def test_storyboard_edit_regenerates_everything_downstream(case):
    case.run()
    case.doctor("edit", target="storyboard", text="add a check-in scene")
    _, issued = case.run()
    assert issued == ["storyboard", "narration", "scene:1", "scene:2", "scene:3", "assemble"]


def test_new_storyboard_scene_count_changes_scene_set(case):
    case.run()
    case.doctor("edit", target="storyboard", text="fewer scenes")

    def outcome(c: Contract) -> dict:
        return {"data": {"scene_count": 2}} if c.subtask == "storyboard" else {}

    _, issued = case.run(outcome)
    assert issued == ["storyboard", "narration", "scene:1", "scene:2", "assemble"]


def test_old_approval_does_not_count_after_edit(case):
    case.run()
    case.doctor("approval")
    case.doctor("edit", target="narration", text="slower")
    decision, issued = case.run()
    assert issued == ["narration", "assemble"]
    assert isinstance(decision, AskDoctor) and decision.kind == "approval"


def test_new_recording_restarts_the_case_and_drops_old_feedback(case):
    case.run()
    case.doctor("edit", target="scene:1", text="old feedback")
    case.doctor("recording")
    contracts: list[Contract] = []

    def outcome(c: Contract) -> dict:
        contracts.append(c)
        return {}

    decision, issued = case.run(outcome)
    assert issued == PIPELINE
    assert all(c.attempt == 1 for c in contracts)
    assert not any("old feedback" in b for c in contracts for b in c.boundaries)
    assert isinstance(decision, AskDoctor) and decision.kind == "approval"


def test_contract_ids_use_round_and_attempt(case):
    case.round = 6
    case.audit(case.step(), status="incomplete")
    assert case.step().id == "c08-transcribe-a2"


# --- log round trip -------------------------------------------------------------------------


def test_input_log_round_trip(tmp_path):
    log = InputLog(tmp_path)
    assert log.read_all() == []
    item = DoctorInput(id="i1", kind="edit", target="scene:1", text="softer")
    log.append(item)
    assert log.read_all() == [item]
