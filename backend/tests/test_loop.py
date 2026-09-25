"""run_case round budget and log reads, with a fake Manager, executor and Auditor."""

import asyncio

import pytest

from backend.app.harness import loop
from backend.app.harness.manager import AskDoctor
from backend.app.state.reports import ReportLog
from backend.app.state.schemas import Contract, ExecutorOutput, Report

MAX_ROUNDS = 3


class AlwaysContract:
    def next_step(self, reports, inputs, round_no):
        return Contract(
            id=f"c{round_no:02d}-transcribe-a1",
            subtask="transcribe",
            executor="transcription",
            goal="g",
            acceptance_criteria=[],
        )


class FakeExecutor:
    async def run(self, contract, workspace):
        return ExecutorOutput(contract_id=contract.id)


class FakeAuditor:
    def audit(self, contract, output, workspace):
        return Report(
            id=f"v-{contract.id}",
            contract_id=contract.id,
            subtask=contract.subtask,
            status="incomplete",
            integrity="clean",
        )


@pytest.fixture
def reads(monkeypatch, tmp_path):
    monkeypatch.setattr(loop.settings, "cases_dir", tmp_path)
    monkeypatch.setattr(loop.settings, "max_rounds", MAX_ROUNDS)
    monkeypatch.setattr(loop, "ManagerAgent", AlwaysContract)
    monkeypatch.setattr(loop, "AuditAgent", FakeAuditor)
    monkeypatch.setattr(loop, "EXECUTORS", {"transcription": FakeExecutor()})

    counter = {"n": 0}
    real_read_all = ReportLog.read_all

    def counting_read_all(self):
        counter["n"] += 1
        return real_read_all(self)

    monkeypatch.setattr(ReportLog, "read_all", counting_read_all)
    return counter


def test_round_budget_is_per_case_not_per_run(reads, tmp_path):
    first = asyncio.run(loop.run_case("c1"))
    assert isinstance(first, AskDoctor) and first.kind == "retries_exhausted"
    assert len(ReportLog(tmp_path / "c1").read_all()) == MAX_ROUNDS

    # A doctor input triggers another run; it must not get a fresh budget.
    second = asyncio.run(loop.run_case("c1"))
    assert isinstance(second, AskDoctor) and second.kind == "retries_exhausted"
    assert len(ReportLog(tmp_path / "c1").read_all()) == MAX_ROUNDS


def test_reports_are_read_once_per_run(reads):
    asyncio.run(loop.run_case("c1"))
    assert reads["n"] == 1
