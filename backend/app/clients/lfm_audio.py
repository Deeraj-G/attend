"""LFM2.5-Audio-1.5B: on-device speech-to-text and text-to-speech."""

import threading
from functools import cached_property
from pathlib import Path

import numpy as np
import soundfile as sf
from pydantic import BaseModel

from backend.app.config import settings

ASR_PROMPT = "Perform ASR."
# Single-pass ASR degrades past ~1 min (drops sentences at ~2 min, loops at ~3 min),
# so long recordings are split at the quietest point in the last part of each window.
CHUNK_SECONDS = 30
SPLIT_SEARCH_SECONDS = 10
# Speech uses ~4 tokens/s, so a 30 s chunk needs ~120. Hitting this cap means the model is looping.
TOKENS_PER_CHUNK = 512
# A 50 ms frame louder than this counts as speech (a quiet room sits around -60 dBFS).
SPEECH_DBFS = -40.0
FRAME_SECONDS = 0.05


class Segment(BaseModel):
    start_s: float
    end_s: float
    text: str
    tokens: int
    speech_s: float  # seconds of frames above SPEECH_DBFS
    truncated: bool  # hit TOKENS_PER_CHUNK even after a retry; likely a repetition loop


class Transcript(BaseModel):
    text: str
    duration_s: float
    model: str
    segments: list[Segment]


def _pick_device() -> str:
    import torch

    if settings.lfm_audio_device != "auto":
        return settings.lfm_audio_device
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _frame_energy(samples: np.ndarray, frame: int) -> np.ndarray:
    return (samples[: len(samples) // frame * frame].reshape(-1, frame) ** 2).mean(axis=1)


def _quietest_cut(samples: np.ndarray, lo: int, hi: int, frame: int) -> int:
    """Sample index at the centre of the lowest-energy frame in samples[lo:hi]."""
    return lo + int(_frame_energy(samples[lo:hi], frame).argmin()) * frame + frame // 2


def split_on_silence(samples: np.ndarray, sample_rate: int) -> list[tuple[int, int]]:
    """(start, end) sample spans of <= CHUNK_SECONDS, each ending at a quiet 50 ms frame near its end."""
    window, search = CHUNK_SECONDS * sample_rate, SPLIT_SEARCH_SECONDS * sample_rate
    frame = int(FRAME_SECONDS * sample_rate)
    spans, start = [], 0
    while len(samples) - start > window:
        cut = _quietest_cut(samples, start + window - search, start + window, frame)
        spans.append((start, cut))
        start = cut
    spans.append((start, len(samples)))
    return spans


def speech_seconds(samples: np.ndarray, sample_rate: int) -> float:
    frame = int(FRAME_SECONDS * sample_rate)
    if len(samples) < frame:
        return 0.0
    dbfs = 10 * np.log10(_frame_energy(samples, frame) + 1e-12)
    return float((dbfs > SPEECH_DBFS).sum() * FRAME_SECONDS)


class LFMAudioClient:
    """Loads the model lazily on first use. Import cost is paid once per process."""

    def __init__(self) -> None:
        self._lock = threading.Lock()  # one generation at a time; the model is not re-entrant

    @cached_property
    def _model(self):  # noqa: ANN202 — liquid_audio types are heavy imports
        import torch
        from liquid_audio import LFM2AudioModel, LFM2AudioProcessor

        repo = str(settings.lfm_audio_model_path or settings.lfm_audio_repo)
        device = _pick_device()
        dtype = torch.float32 if device == "cpu" else torch.bfloat16
        processor = LFM2AudioProcessor.from_pretrained(repo, device=device).eval()
        model = LFM2AudioModel.from_pretrained(repo, device=device, dtype=dtype).eval()
        return processor, model

    def load(self) -> None:
        """Warm the model so the first request doesn't pay the load time."""
        _ = self._model

    def transcribe(self, audio_path: Path) -> Transcript:
        wave, sample_rate = sf.read(audio_path, dtype="float32", always_2d=True)
        mono = wave.mean(axis=1)
        with self._lock:
            segments = [
                seg
                for start, end in split_on_silence(mono, sample_rate)
                for seg in self._transcribe_span(mono, start, end, sample_rate, retry=True)
            ]
        return Transcript(
            text=" ".join(s.text for s in segments if s.text),
            duration_s=round(len(mono) / sample_rate, 2),
            model=str(settings.lfm_audio_model_path or settings.lfm_audio_repo),
            segments=segments,
        )

    def _transcribe_span(
        self, mono: np.ndarray, start: int, end: int, sample_rate: int, *, retry: bool
    ) -> list[Segment]:
        samples = mono[start:end]
        text, tokens = self._transcribe_chunk(samples, sample_rate)
        truncated = tokens >= TOKENS_PER_CHUNK
        # Decoding is greedy, so re-running the same audio loops the same way. Retry as two halves.
        if truncated and retry and end - start > 2 * sample_rate:
            quarter, frame = (end - start) // 4, int(FRAME_SECONDS * sample_rate)
            mid = _quietest_cut(mono, start + quarter, end - quarter, frame)
            return [
                *self._transcribe_span(mono, start, mid, sample_rate, retry=False),
                *self._transcribe_span(mono, mid, end, sample_rate, retry=False),
            ]
        return [
            Segment(
                start_s=round(start / sample_rate, 2),
                end_s=round(end / sample_rate, 2),
                text=text,
                tokens=tokens,
                speech_s=round(speech_seconds(samples, sample_rate), 2),
                truncated=truncated,
            )
        ]

    def _transcribe_chunk(self, samples: np.ndarray, sample_rate: int) -> tuple[str, int]:
        import torch
        from liquid_audio import ChatState

        processor, model = self._model
        chat = ChatState(processor)
        chat.new_turn("system")
        chat.add_text(ASR_PROMPT)
        chat.end_turn()
        chat.new_turn("user")
        chat.add_audio(torch.from_numpy(samples).unsqueeze(0), sample_rate)
        chat.end_turn()
        chat.new_turn("assistant")

        generated = list(model.generate_sequential(**chat, max_new_tokens=TOKENS_PER_CHUNK))
        text_tokens = [t for t in generated if t.numel() == 1]
        if not text_tokens:
            return "", len(generated)
        return processor.text.decode(torch.cat(text_tokens), skip_special_tokens=True).strip(), len(generated)

    def synthesize(self, text: str, out_path: Path) -> Path:
        raise NotImplementedError


lfm_audio = LFMAudioClient()
