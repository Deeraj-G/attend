"""Black Forest Labs scene generation. Prompts must be de-identified."""

from pathlib import Path

from backend.app.config import settings


class BFLClient:
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or settings.bfl_api_key

    async def generate_scene(self, prompt: str, out_path: Path) -> Path:
        raise NotImplementedError
