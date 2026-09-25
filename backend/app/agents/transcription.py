"""Doctor audio -> transcript, on device (LFM2.5-Audio STT)."""

import asyncio

import soundfile as sf

from backend.app.clients.lfm_audio import lfm_audio
from backend.app.state.schemas import Contract, ExecutorName, ExecutorOutput
from backend.app.state.workspace import Workspace


def transcription_contract(contract_id: str = "c1") -> Contract:
    """The c1 contract, until the Manager emits it itself."""
    return Contract(
        id=contract_id,
        executor=ExecutorName.TRANSCRIPTION,
        goal="Transcribe the doctor's procedure description on device.",
        acceptance_criteria=[f"{Workspace.TRANSCRIPT} exists and is non-empty"],
        boundaries=["no network calls", f"write only {Workspace.TRANSCRIPT}"],
    )


class TranscriptionAgent:
    name = "transcription"

    async def run(self, contract: Contract, workspace: Workspace) -> ExecutorOutput:
        audio = workspace.path(Workspace.AUDIO)
        if not audio.exists():
            return ExecutorOutput(contract_id=contract.id, summary=f"missing input: {Workspace.AUDIO}")

        # Model inference is blocking; keep the event loop free for the trace socket.
        text = await asyncio.to_thread(lfm_audio.transcribe, audio)
        workspace.path(Workspace.TRANSCRIPT).write_text(text + "\n")
        workspace.record_provenance(Workspace.TRANSCRIPT, self.name)

        # The summary goes to the Auditor; keep transcript content (possible PHI) out of it.
        seconds = sf.info(audio).duration
        return ExecutorOutput(
            contract_id=contract.id,
            artifacts=[Workspace.TRANSCRIPT],
            summary=f"{len(text.split())} words from {seconds:.1f}s of audio",
        )
