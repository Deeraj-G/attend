"""Generate one scene clip per contract via Black Forest Labs. Calm, non-graphic."""

from backend.app.state.schemas import Contract, ExecutorOutput
from backend.app.state.workspace import Workspace


class VideoGenerationAgent:
    name = "video_generation"

    async def run(self, contract: Contract, workspace: Workspace) -> ExecutorOutput:
        raise NotImplementedError
