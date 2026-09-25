"""Doctor audio -> transcript, on device (LFM2.5-Audio STT)."""

import asyncio

from backend.app.clients.lfm_audio import lfm_audio
from backend.app.state.schemas import Contract, ExecutorName, ExecutorOutput
from backend.app.state.workspace import Workspace

# Measured ~3.7-4.0 words per voiced second on clean speech, ~10.8 when the model looped.
# Below the band the transcript has probably lost audio; above it, it has probably looped.
WORDS_PER_SPEECH_SECOND = (0.8, 6.0)


def transcription_contract(contract_id: str = "c1") -> Contract:
    """The c1 contract, until the Manager emits it itself."""
    lo, hi = WORDS_PER_SPEECH_SECOND
    return Contract(
        id=contract_id,
        subtask="transcribe",
        executor=ExecutorName.TRANSCRIPTION,
        goal="Transcribe the doctor's procedure description on device.",
        acceptance_criteria=[
            f"{Workspace.TRANSCRIPT} exists and is non-empty",
            "data.empty_segments == 0 (no segment with speech came back empty)",
            "data.truncated_segments == 0 (no segment hit the token cap)",
            f"{lo} <= data.words_per_speech_second <= {hi}",
        ],
        boundaries=[
            "no network calls",
            f"write only {Workspace.TRANSCRIPT}, {Workspace.TRANSCRIPT_JSON}, {Workspace.PROVENANCE}",
        ],
    )


class TranscriptionAgent:
    name = "transcription"

    async def run(self, contract: Contract, workspace: Workspace) -> ExecutorOutput:
        audio = workspace.path(Workspace.AUDIO)
        if not audio.exists():
            return ExecutorOutput(contract_id=contract.id, summary=f"missing input: {Workspace.AUDIO}")

        # Model inference is blocking; keep the event loop free for the trace socket.
        transcript = await asyncio.to_thread(lfm_audio.transcribe, audio)
        # transcript.txt is the input to de-identification; transcript.json keeps per-segment detail.
        workspace.path(Workspace.TRANSCRIPT).write_text(transcript.text + "\n")
        workspace.path(Workspace.TRANSCRIPT_JSON).write_text(transcript.model_dump_json(indent=2))
        for artifact in (Workspace.TRANSCRIPT, Workspace.TRANSCRIPT_JSON):
            workspace.record_provenance(artifact, self.name)

        # Everything below goes to the Auditor; keep transcript content (possible PHI) out of it.
        segments = transcript.segments
        words = len(transcript.text.split())
        speech_s = sum(s.speech_s for s in segments)
        data = {
            "duration_s": transcript.duration_s,
            "speech_s": round(speech_s, 2),
            "words": words,
            "segment_count": len(segments),
            # Silent stretches legitimately transcribe to nothing; only speech that did is a gap.
            "empty_segments": sum(1 for s in segments if not s.text and s.speech_s >= 1.0),
            "truncated_segments": sum(1 for s in segments if s.truncated),
            "words_per_speech_second": round(words / speech_s, 2) if speech_s else 0.0,
        }
        flags = [f"{data[k]} {k.replace('_', ' ')}" for k in ("empty_segments", "truncated_segments") if data[k]]
        return ExecutorOutput(
            contract_id=contract.id,
            artifacts=[Workspace.TRANSCRIPT, Workspace.TRANSCRIPT_JSON],
            summary=f"{words} words from {transcript.duration_s:.1f}s of audio"
            + (f" ({', '.join(flags)})" if flags else ""),
            data=data,
        )
