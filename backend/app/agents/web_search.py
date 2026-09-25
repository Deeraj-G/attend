"""Research the procedure via Nimble text/image/video search. Media results are prompt references only."""

from backend.app.state.schemas import Contract, ExecutorOutput
from backend.app.state.workspace import Workspace


class WebSearchAgent:
    name = "web_search"

    async def run(self, contract: Contract, workspace: Workspace) -> ExecutorOutput:
        raise NotImplementedError
