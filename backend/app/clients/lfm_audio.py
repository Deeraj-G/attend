"""LFM2.5-Audio-1.5B: on-device speech-to-text and text-to-speech."""

import threading
from functools import cached_property
from pathlib import Path

import numpy as np
import soundfile as sf

from backend.app.config import settings

ASR_PROMPT = "Perform ASR."
# Single-pass ASR degrades past ~1 min (drops sentences at ~2 min, loops at ~3 min),
# so long recordings are split at the quietest point in the last part of each window.
CHUNK_SECONDS = 30
SPLIT_SEARCH_SECONDS = 10
# ASR output is roughly 3 tokens per second of speech; leave generous headroom.
TOKENS_PER_CHUNK = 512


def _pick_device() -> str:
    import torch

    if settings.lfm_audio_device != "auto":
        return settings.lfm_audio_device
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def split_on_silence(samples: np.ndarray, sample_rate: int) -> list[np.ndarray]:
    """Cut into <= CHUNK_SECONDS pieces, each ending at the lowest-energy 50 ms frame near its end."""
    window, search = CHUNK_SECONDS * sample_rate, SPLIT_SEARCH_SECONDS * sample_rate
    frame = sample_rate // 20
    chunks, start = [], 0
    while len(samples) - start > window:
        region = samples[start + window - search : start + window]
        energy = (region[: len(region) // frame * frame].reshape(-1, frame) ** 2).mean(axis=1)
        cut = start + window - search + int(energy.argmin()) * frame + frame // 2
        chunks.append(samples[start:cut])
        start = cut
    chunks.append(samples[start:])
    return chunks


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

    def transcribe(self, audio_path: Path) -> str:
        wave, sample_rate = sf.read(audio_path, dtype="float32", always_2d=True)
        chunks = split_on_silence(wave.mean(axis=1), sample_rate)
        with self._lock:
            parts = [self._transcribe_chunk(c, sample_rate) for c in chunks if len(c) > sample_rate // 10]
        return " ".join(p for p in parts if p)

    def _transcribe_chunk(self, samples: np.ndarray, sample_rate: int) -> str:
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

        tokens = [t for t in model.generate_sequential(**chat, max_new_tokens=TOKENS_PER_CHUNK) if t.numel() == 1]
        if not tokens:
            return ""
        return processor.text.decode(torch.cat(tokens), skip_special_tokens=True).strip()

    def synthesize(self, text: str, out_path: Path) -> Path:
        raise NotImplementedError


lfm_audio = LFMAudioClient()
