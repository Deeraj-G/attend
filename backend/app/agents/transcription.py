"""Doctor audio -> transcript, on device (LFM2.5-Audio STT)."""

from backend.app.state.schemas import Contract, ExecutorOutput
from backend.app.state.workspace import Workspace


class TranscriptionAgent:
    name = "transcription"

    async def run(self, contract: Contract, workspace: Workspace) -> ExecutorOutput:
        raise NotImplementedError
