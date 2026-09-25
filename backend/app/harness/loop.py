"""Manage -> Execute -> Audit round driver."""

from backend.app.agents import EXECUTORS
from backend.app.config import settings
from backend.app.harness.auditor import AuditAgent
from backend.app.harness.manager import AskDoctor, Done, ManagerAgent
from backend.app.state.reports import ReportLog
from backend.app.state.schemas import Contract
from backend.app.state.workspace import Workspace


async def run_case(case_id: str, task: str) -> AskDoctor | Done:
    """Run rounds until the Manager is done or needs the doctor."""
    workspace = Workspace(case_id)
    log = ReportLog(workspace.dir)
    manager, auditor = ManagerAgent(), AuditAgent()

    for _ in range(settings.max_rounds):
        decision = manager.next_step(task, log.read_all())
        if not isinstance(decision, Contract):
            return decision
        output = await EXECUTORS[decision.executor].run(decision, workspace)
        log.append(auditor.audit(decision, output, workspace))

    return AskDoctor(question="Round budget exhausted. Please review the case.")
