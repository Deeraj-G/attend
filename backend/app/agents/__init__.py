from backend.app.agents.assembly import AssemblyAgent
from backend.app.agents.base import Executor
from backend.app.agents.deidentify import DeidentifyAgent
from backend.app.agents.script import ScriptAgent
from backend.app.agents.transcription import TranscriptionAgent
from backend.app.agents.video_generation import VideoGenerationAgent
from backend.app.agents.web_search import WebSearchAgent
from backend.app.agents.verification import VerificationAgent
from backend.app.state.schemas import ExecutorName

EXECUTORS: dict[ExecutorName, Executor] = {
    ExecutorName.TRANSCRIPTION: TranscriptionAgent(),
    ExecutorName.DEIDENTIFY: DeidentifyAgent(),
    ExecutorName.WEB_SEARCH: WebSearchAgent(),
    ExecutorName.VERIFICATION: VerificationAgent(),
    ExecutorName.SCRIPT: ScriptAgent(),
    ExecutorName.VIDEO_GENERATION: VideoGenerationAgent(),
    ExecutorName.ASSEMBLY: AssemblyAgent(),
}
