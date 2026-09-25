"""LFM2.5-2.6B (Q4, llama.cpp) with JSON-schema constrained output."""

from pydantic import BaseModel


class LFMClient:
    def generate(self, prompt: str, max_tokens: int = 512) -> str:
        raise NotImplementedError

    def generate_structured[T: BaseModel](self, prompt: str, schema: type[T]) -> T:
        raise NotImplementedError
