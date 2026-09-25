from pathlib import Path

from backend.app.config import settings


class Workspace:
    """Per-case environment folder: cases/<case_id>/.

    Executors read and write here. The Auditor reads only. The Manager has no access.
    """

    def __init__(self, case_id: str, root: Path | None = None) -> None:
        self.case_id = case_id
        self.dir = (root or settings.cases_dir) / case_id
        self.dir.mkdir(parents=True, exist_ok=True)

    def path(self, relative: str) -> Path:
        return self.dir / relative

    def record_provenance(self, relative: str, executor: str) -> None:
        """Record which executor wrote an artifact, for the Auditor's provenance check."""
        raise NotImplementedError

    def provenance(self) -> dict[str, str]:
        raise NotImplementedError
