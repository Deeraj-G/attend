"""Contract templates, one per subtask (ADR 0004, "Resulting contracts")."""

from dataclasses import dataclass

from backend.app.agents.transcription import transcription_contract
from backend.app.agents.web_search import research_contract
from backend.app.state.schemas import Contract, ExecutorName


@dataclass(frozen=True)
class Template:
    executor: ExecutorName
    goal: str
    acceptance_criteria: tuple[str, ...]
    boundaries: tuple[str, ...]


def _from_contract(c: Contract) -> Template:
    """Executors own their contract definitions; reuse them so the two can't drift."""
    return Template(c.executor, c.goal, tuple(c.acceptance_criteria), tuple(c.boundaries))


TEMPLATES: dict[str, Template] = {
    "transcribe": _from_contract(transcription_contract()),
    "deidentify": Template(
        executor=ExecutorName.DEIDENTIFY,
        goal="Produce a de-identified procedure brief from the transcript.",
        acceptance_criteria=(
            "brief.json has a non-empty procedure",
            "data.phi_remaining == 0 (no identifiers left in brief.json)",
        ),
        boundaries=("on device only; no network calls", "read transcript.txt; write only brief.json"),
    ),
    "research": _from_contract(research_contract()),
    "video": Template(
        executor=ExecutorName.VIDEO_GENERATION,
        goal="Generate one calm, non-graphic patient-education video from the brief and verified sources.",
        acceptance_criteria=("video.json has status Ready and an HTTPS sample_url",),
        boundaries=(
            "prompt built from brief.json and sources.json only; never the transcript",
            "write only video.json",
        ),
    ),
}


def template_key(subtask: str) -> str:
    """'scene:3' -> 'scene'; everything else maps to itself."""
    return subtask.split(":", 1)[0]


def build_contract(
    subtask: str,
    attempt: int,
    round_no: int,
    related_reports: list[str],
    extra_acceptance: list[str] | None = None,
    extra_boundaries: list[str] | None = None,
) -> Contract:
    template = TEMPLATES[template_key(subtask)]
    n = subtask.split(":", 1)[1] if ":" in subtask else ""
    return Contract(
        id=f"c{round_no:02d}-{subtask.replace(':', '-')}-a{attempt}",
        subtask=subtask,
        attempt=attempt,
        executor=template.executor,
        goal=template.goal.format(n=n),
        acceptance_criteria=[a.format(n=n) for a in template.acceptance_criteria] + (extra_acceptance or []),
        boundaries=[b.format(n=n) for b in template.boundaries] + (extra_boundaries or []),
        related_reports=related_reports,
    )
