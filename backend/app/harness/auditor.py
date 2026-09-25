"""AuditAgent. Read-only, clean context. Checks provenance, mutations and PHI; writes report V_i."""

from backend.app.state.schemas import Contract, ExecutorOutput, Report
from backend.app.state.workspace import Workspace


class AuditAgent:
    def audit(self, contract: Contract, output: ExecutorOutput, workspace: Workspace) -> Report:
        raise NotImplementedError
