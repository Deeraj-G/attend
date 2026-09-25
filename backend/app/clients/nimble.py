"""Nimble web search: text, image and video. Callers must pass de-identified queries only.

- text:  POST /search (general web search)
- image: POST /serp with search_engine=google_images
- video: POST /search restricted to video hosts (Nimble has no video SERP engine)

Every result is normalised to {kind, url, title, snippet, domain, thumbnail_url, image_url}.
"""

from typing import Literal
from urllib.parse import urlparse

import httpx

from backend.app.config import settings
from backend.app.phi import contains_phi

SearchKind = Literal["text", "image", "video"]

VIDEO_DOMAINS = ["youtube.com", "vimeo.com"]


class PHIBlockedError(ValueError):
    """Raised instead of sending a query that looks like it contains PHI."""


class NimbleClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = (api_key or settings.nimble_api_key).strip()
        self.base_url = (base_url or settings.nimble_api_base).rstrip("/")
        self._transport = transport  # tests inject httpx.MockTransport

    async def search(
        self,
        query: str,
        kind: SearchKind = "text",
        max_results: int | None = None,
        include_domains: list[str] | None = None,
    ) -> list[dict]:
        if contains_phi(query):
            raise PHIBlockedError("Outbound Nimble query blocked: possible PHI")

        n = max_results or settings.nimble_results_per_call
        if kind == "image":
            raw = await self._post(
                "/serp",
                {"search_engine": "google_images", "query": query, "num_results": n, "country": "US"},
            )
            return _normalise_images(raw)[:n]  # google_images ignores num_results (returns ~100)

        payload: dict = {"query": query, "max_results": n}
        domains = VIDEO_DOMAINS if kind == "video" else include_domains
        if domains:
            payload["include_domains"] = domains
        raw = await self._post("/search", payload)
        return _normalise_search(raw, kind)

    async def _post(self, path: str, payload: dict) -> dict:
        if not self.api_key:
            raise RuntimeError("NIMBLE_API_KEY is not set (add it to .env in the project root)")
        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=settings.nimble_timeout_seconds,
            transport=self._transport,
        ) as client:
            resp = await client.post(
                path, json=payload, headers={"Authorization": f"Bearer {self.api_key}"}
            )
            resp.raise_for_status()
            return resp.json()


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host.removeprefix("www.")


def _normalise_search(raw: dict, kind: SearchKind) -> list[dict]:
    out = []
    for r in raw.get("results") or []:
        url = r.get("url") or ""
        if not url:
            continue
        out.append(
            {
                "kind": kind,
                "url": url,
                "title": r.get("title") or "",
                "snippet": r.get("description") or r.get("content") or "",
                "domain": _domain(url),
                "thumbnail_url": None,
                "image_url": None,
            }
        )
    return out


def _normalise_images(raw: dict) -> list[dict]:
    # Real responses: data.parsing.entities.ImageResult[] with image_url, source_url,
    # thumbnail_url, title, source_name. Fallback keys kept in case the shape shifts.
    entities = (((raw.get("data") or {}).get("parsing") or {}).get("entities")) or {}
    items: list[dict] = []
    for key, value in entities.items():
        if "image" in key.lower() and isinstance(value, list):
            items.extend(v for v in value if isinstance(v, dict))

    out = []
    for r in items:
        source = r.get("source_url") or r.get("url") or r.get("link") or ""
        image = r.get("image_url") or r.get("original") or r.get("image") or ""
        if not (source or image):
            continue
        out.append(
            {
                "kind": "image",
                "url": source or image,
                "title": r.get("title") or r.get("alt") or "",
                "snippet": r.get("source_name") or r.get("source") or "",
                "domain": _domain(source or image),
                "thumbnail_url": r.get("thumbnail_url") or r.get("thumbnail"),
                "image_url": image or None,
            }
        )
    return out
