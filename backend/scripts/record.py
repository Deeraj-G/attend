"""Record from the mic into a case workspace, optionally transcribe.

    python -m backend.scripts.record                 # new case, press Enter to stop
    python -m backend.scripts.record --transcribe    # ...then run step 1
    python -m backend.scripts.record --file a.wav    # skip the mic, import a file
"""

import argparse
import asyncio
import queue
import uuid
from pathlib import Path

import numpy as np

from backend.app.agents.transcription import TranscriptionAgent, transcription_contract
from backend.app.recorder import save_recording, save_upload
from backend.app.state.schemas import Case
from backend.app.state.workspace import Workspace

SAMPLE_RATE = 16_000


def record_until_enter() -> np.ndarray:
    import sounddevice as sd

    blocks: queue.Queue[np.ndarray] = queue.Queue()
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32", callback=lambda d, *_: blocks.put(d.copy())):
        input("Recording... press Enter to stop. ")
    return np.concatenate(list(blocks.queue)) if not blocks.empty() else np.zeros((0, 1), dtype="float32")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--case", help="existing case id (default: create one)")
    parser.add_argument("--file", type=Path, help="import an audio file instead of recording")
    parser.add_argument("--transcribe", action="store_true", help="run the transcription agent afterwards")
    args = parser.parse_args()

    if args.case:
        workspace = Workspace(args.case)
        if not workspace.exists():
            parser.error(f"case {args.case} not found")
    else:
        case = Case(id=uuid.uuid4().hex[:12])
        workspace = Workspace(case.id)
        workspace.save_case(case)

    if args.file:
        duration = save_upload(workspace, args.file.read_bytes())
    else:
        duration = save_recording(workspace, record_until_enter(), SAMPLE_RATE)
    print(f"case {workspace.case_id}: saved {duration:.1f}s -> {workspace.path(Workspace.AUDIO)}")

    if args.transcribe:
        print("Transcribing on device (first run loads the model)...")
        output = asyncio.run(TranscriptionAgent().run(transcription_contract(), workspace))
        print(output.summary)
        print(output.data)
        print(workspace.path(Workspace.TRANSCRIPT).read_text())


if __name__ == "__main__":
    main()
