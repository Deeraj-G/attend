from pathlib import Path

from backend.app.state.schemas import Report


class ReportLog:
    """Append-only reports.jsonl for a case (External State Memory)."""

    def __init__(self, case_dir: Path) -> None:
        self.path = case_dir / "reports.jsonl"

    def append(self, report: Report) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            f.write(report.model_dump_json() + "\n")

    def read_all(self) -> list[Report]:
        if not self.path.exists():
            return []
        with self.path.open() as f:
            return [Report.model_validate_json(line) for line in f if line.strip()]
