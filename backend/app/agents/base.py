from typing import Protocol

from backend.app.state.schemas import Contract, ExecutorOutput
from backend.app.state.workspace import Workspace


class Executor(Protocol):
    """Runs one contract in a fresh, budgeted context. Sees the workspace and related reports only."""

    name: str

    async def run(self, contract: Contract, workspace: Workspace) -> ExecutorOutput: ...
