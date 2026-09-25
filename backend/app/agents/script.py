"""Storyboard + narration script (6th-8th grade reading level), voiced with LFM2.5-Audio TTS."""

from backend.app.state.schemas import Contract, ExecutorOutput
from backend.app.state.workspace import Workspace


class ScriptAgent:
    name = "script"

    async def run(self, contract: Contract, workspace: Workspace) -> ExecutorOutput:
        raise NotImplementedError
