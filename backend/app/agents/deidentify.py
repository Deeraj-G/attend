"""Transcript -> de-identified procedure brief. The only text allowed to leave the device."""

from backend.app.state.schemas import Contract, ExecutorOutput
from backend.app.state.workspace import Workspace


class DeidentifyAgent:
    name = "deidentify"

    async def run(self, contract: Contract, workspace: Workspace) -> ExecutorOutput:
        raise NotImplementedError
