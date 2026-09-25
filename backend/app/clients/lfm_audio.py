"""LFM2.5-Audio-1.5B: on-device speech-to-text and text-to-speech."""

from pathlib import Path


class LFMAudioClient:
    def transcribe(self, audio_path: Path) -> str:
        raise NotImplementedError

    def synthesize(self, text: str, out_path: Path) -> Path:
        raise NotImplementedError
