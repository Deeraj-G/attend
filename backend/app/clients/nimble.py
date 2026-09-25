"""Nimble web search: text, image and video. Callers must pass de-identified queries only."""

from typing import Literal

from backend.app.config import settings


class NimbleClient:
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or settings.nimble_api_key

    async def search(
        self, query: str, kind: Literal["text", "image", "video"] = "text"
    ) -> list[dict]:
        raise NotImplementedError
