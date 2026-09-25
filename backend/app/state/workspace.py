import hashlib
import json
from pathlib import Path

from backend.app.config import settings
from backend.app.state.schemas import Artifact, Case


class Workspace:
    """Per-case environment folder: cases/<case_id>/.

    Executors read and write here. The Auditor reads only. The Manager has no access.
    """

    AUDIO = "audio/recording.wav"
    TRANSCRIPT = "transcript.txt"
    TRANSCRIPT_JSON = "transcript.json"
    PROVENANCE = "provenance.json"

    def __init__(self, case_id: str, root: Path | None = None) -> None:
        self.case_id = case_id
        self.dir = (root or settings.cases_dir) / case_id
        self.dir.mkdir(parents=True, exist_ok=True)

    @property
    def _case_file(self) -> Path:
        return self.dir / "case.json"

    @property
    def _provenance_file(self) -> Path:
        return self.dir / self.PROVENANCE

    def path(self, relative: str) -> Path:
        return self.dir / relative

    def exists(self) -> bool:
        return self._case_file.exists()

    def load_case(self) -> Case:
        return Case.model_validate_json(self._case_file.read_text())

    def save_case(self, case: Case) -> None:
        self._case_file.write_text(case.model_dump_json(indent=2))

    def record_provenance(self, relative: str, executor: str) -> None:
        """Record which executor wrote an artifact, for the Auditor's provenance check."""
        sha256 = hashlib.sha256(self.path(relative).read_bytes()).hexdigest()
        entries = self.provenance()
        entries[relative] = Artifact(path=relative, written_by=executor, sha256=sha256)
        self._provenance_file.write_text(
            json.dumps({k: v.model_dump() for k, v in entries.items()}, indent=2)
        )

    def provenance(self) -> dict[str, Artifact]:
        if not self._provenance_file.exists():
            return {}
        raw = json.loads(self._provenance_file.read_text())
        return {k: Artifact.model_validate(v) for k, v in raw.items()}
