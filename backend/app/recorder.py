"""Step 0: capture the doctor's description into the case workspace (on device only)."""

import io

import numpy as np
import soundfile as sf

from backend.app.config import settings
from backend.app.state.workspace import Workspace

WRITER = "recorder"


class RecordingError(ValueError):
    pass


def save_recording(workspace: Workspace, samples: np.ndarray, sample_rate: int) -> float:
    """Write mono 16-bit WAV to the workspace and record provenance. Returns duration in seconds."""
    if samples.ndim == 2:
        samples = samples.mean(axis=1)
    duration = len(samples) / sample_rate
    if duration < 0.5:
        raise RecordingError("recording is shorter than 0.5s")
    if duration > settings.max_recording_seconds:
        raise RecordingError(f"recording exceeds {settings.max_recording_seconds}s")

    out = workspace.path(Workspace.AUDIO)
    out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(out, samples, sample_rate, subtype="PCM_16")
    workspace.record_provenance(Workspace.AUDIO, WRITER)
    return duration


def save_upload(workspace: Workspace, data: bytes) -> float:
    """Accepts anything libsndfile reads (WAV, FLAC, OGG, MP3)."""
    try:
        samples, sample_rate = sf.read(io.BytesIO(data), dtype="float32", always_2d=True)
    except sf.LibsndfileError as e:
        raise RecordingError(f"unreadable audio: {e}") from e
    return save_recording(workspace, samples, sample_rate)
