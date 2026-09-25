from pathlib import Path

from backend.app.state.schemas import DoctorInput


class InputLog:
    """Append-only inputs.jsonl for a case: everything the doctor sends back."""

    def __init__(self, case_dir: Path) -> None:
        self.path = case_dir / "inputs.jsonl"

    def append(self, doctor_input: DoctorInput) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            f.write(doctor_input.model_dump_json() + "\n")

    def read_all(self) -> list[DoctorInput]:
        if not self.path.exists():
            return []
        with self.path.open() as f:
            return [DoctorInput.model_validate_json(line) for line in f if line.strip()]
