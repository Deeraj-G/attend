"""ManagerAgent (LFM2.5-2.6B). Reads audit reports only, never the workspace."""

from dataclasses import dataclass

from backend.app.state.schemas import Contract, Report


@dataclass
class AskDoctor:
    """Ask route: conflicts, blocked subtasks, and the final approval gate."""

    question: str


@dataclass
class Done:
    pass


type ManagerDecision = Contract | AskDoctor | Done


class ManagerAgent:
    def next_step(self, task: str, reports: list[Report]) -> ManagerDecision:
        raise NotImplementedError
