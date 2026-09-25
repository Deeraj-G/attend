"""Stitch scene clips, narration and captions into the final video with ffmpeg."""

from backend.app.state.schemas import Contract, ExecutorOutput
from backend.app.state.workspace import Workspace


class AssemblyAgent:
    name = "assembly"

    async def run(self, contract: Contract, workspace: Workspace) -> ExecutorOutput:
        raise NotImplementedError
