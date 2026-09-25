"""Contract templates, one per subtask (ADR 0004, "Resulting contracts")."""

from dataclasses import dataclass

from backend.app.state.schemas import Contract, ExecutorName


@dataclass(frozen=True)
class Template:
    executor: ExecutorName
    goal: str
    acceptance_criteria: tuple[str, ...]
    boundaries: tuple[str, ...]


TEMPLATES: dict[str, Template] = {
    "transcribe": Template(
        executor=ExecutorName.TRANSCRIPTION,
        goal="Transcribe the doctor's recording on device.",
        acceptance_criteria=(
            "transcript.txt exists and is non-empty",
            "no empty or truncated segments; report data.duration_s",
        ),
        boundaries=("on device only; no network calls", "write only transcript.txt and transcript.json"),
    ),
    "deidentify": Template(
        executor=ExecutorName.DEIDENTIFY,
        goal="Produce a de-identified procedure brief from the transcript.",
        acceptance_criteria=(
            "brief.json has procedure, steps[] and patient_concerns[]",
            "no names, dates, MRNs or other identifiers",
        ),
        boundaries=("on device only; no network calls", "read transcript.txt; write only brief.json"),
    ),
    "research": Template(
        executor=ExecutorName.WEB_SEARCH,
        goal="Research the procedure for patient education, using the brief.",
        acceptance_criteria=(
            "sources.json has >= 3 authoritative sources",
            "sources cover prep, procedure, recovery and going home",
        ),
        boundaries=(
            "outbound queries built from brief.json only",
            "exclude forums and marketing pages",
            "media results are references only, never output",
            "web sources must not contradict the brief",
            "write only sources.json and media_refs.json",
        ),
    ),
    "storyboard": Template(
        executor=ExecutorName.SCRIPT,
        goal="Break the procedure into 4-6 calm, non-graphic scenes.",
        acceptance_criteria=(
            "storyboard.json has 4-6 scenes, each with title, description and visual prompt",
            "report data.scene_count",
        ),
        boundaries=("the doctor's brief is the source of truth", "write only storyboard.json"),
    ),
    "narration": Template(
        executor=ExecutorName.SCRIPT,
        goal="Write and voice the narration script.",
        acceptance_criteria=(
            "script.txt is at a 6th-8th grade reading level, one section per scene",
            "narration.wav exists",
        ),
        boundaries=("TTS on device", "follow storyboard.json", "write only script.txt and narration.wav"),
    ),
    "scene": Template(
        executor=ExecutorName.VIDEO_GENERATION,
        goal="Generate the clip for scene {n}.",
        acceptance_criteria=("scenes/scene_{n}.mp4 exists and matches the scene's visual prompt",),
        boundaries=(
            "calm, illustrative, non-graphic style",
            "prompt must be de-identified",
            "write only scenes/scene_{n}.mp4",
        ),
    ),
    "assemble": Template(
        executor=ExecutorName.ASSEMBLY,
        goal="Stitch the scene clips, narration and captions into the final video.",
        acceptance_criteria=(
            "final.mp4 exists with all scenes in order",
            "audio length matches the narration",
        ),
        boundaries=("local ffmpeg only", "write only final.mp4"),
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
