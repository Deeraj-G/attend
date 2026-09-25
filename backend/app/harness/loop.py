"""Manage -> Execute -> Audit round driver."""

import asyncio

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
    # Read once: only this loop appends reports, and doctor inputs arrive between runs.
    all_reports, all_inputs = reports.read_all(), inputs.read_all()

    # One report per round, so round numbers count across runs and max_rounds caps the case.
    for round_no in range(len(all_reports) + 1, settings.max_rounds + 1):
        decision = manager.next_step(all_reports, all_inputs, round_no)
        if not isinstance(decision, Contract):
            return decision
        output = await EXECUTORS[decision.executor].run(decision, workspace)
        # The verifier runs the LFM; keep the event loop free for other requests.
        report = await asyncio.to_thread(auditor.audit, decision, output, workspace)
        reports.append(report)
        all_reports.append(report)

    return AskDoctor(kind="retries_exhausted", question="Round budget exhausted. Please review the case.")
