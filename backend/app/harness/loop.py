"""Manage -> Execute -> Audit round driver."""

from backend.app.agents import EXECUTORS
from backend.app.config import settings
from backend.app.harness.auditor import AuditAgent
from backend.app.harness.manager import AskDoctor, Done, ManagerAgent
from backend.app.state.inputs import InputLog
from backend.app.state.reports import ReportLog
from backend.app.state.schemas import Contract
from backend.app.state.workspace import Workspace


async def run_case(case_id: str) -> AskDoctor | Done:
    """Run rounds until the Manager is done or needs the doctor. Re-run on each doctor input."""
    workspace = Workspace(case_id)
    reports, inputs = ReportLog(workspace.dir), InputLog(workspace.dir)
    manager, auditor = ManagerAgent(), AuditAgent()
    start = len(reports.read_all()) + 1

    for round_no in range(start, start + settings.max_rounds):
        decision = manager.next_step(reports.read_all(), inputs.read_all(), round_no)
        if not isinstance(decision, Contract):
            return decision
        output = await EXECUTORS[decision.executor].run(decision, workspace)
        reports.append(auditor.audit(decision, output, workspace))

    return AskDoctor(kind="retries_exhausted", question="Round budget exhausted. Please review the case.")
