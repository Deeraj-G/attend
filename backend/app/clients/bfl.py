"""Server-side FLUX 3 client. Callers supply de-identified educational material."""
from urllib.parse import urlsplit

import httpx

from backend.app.config import settings


class BFLError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


def validate_polling_url(url: str) -> str:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise BFLError("BFL returned an invalid polling URL") from exc
    host = parsed.hostname or ""
    if (parsed.scheme != "https" or parsed.username or parsed.password
            or port not in (None, 443)
            or not (host == "api.bfl.ai" or host.endswith(".bfl.ai"))):
        raise BFLError("BFL returned an untrusted polling URL")
    return url


class BFLClient:
    def __init__(self, api_key: str | None = None, transport=None) -> None:
        self.api_key = api_key if api_key is not None else settings.bfl_api_key
        self.transport = transport

    async def _request(self, method: str, url: str, **kwargs) -> dict:
        if not self.api_key:
            raise BFLError("Set BFL_API_KEY in the backend .env before generating.", 503)
        try:
            async with httpx.AsyncClient(timeout=60, follow_redirects=False, transport=self.transport) as client:
                response = await client.request(method, url, headers={"x-key": self.api_key}, **kwargs)
            if response.status_code >= 300:
                messages = {401: "BFL API key is invalid.", 402: "BFL credits are insufficient.",
                            403: "BFL denied access to this model.", 429: "BFL is rate limited; try again later.",
                            422: "BFL rejected the generation parameters or input image."}
                raise BFLError(messages.get(response.status_code, "BFL request failed."))
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("expected object")
            return data
        except httpx.TimeoutException as exc:
            raise BFLError("BFL timed out. A submitted job may still be running; do not automatically resubmit.", 504) from exc
        except (httpx.RequestError, ValueError) as exc:
            raise BFLError("Could not read a valid response from BFL.") from exc

    async def submit(self, payload: dict) -> dict:
        data = await self._request("POST", "https://api.bfl.ai/v1/flux-3-video", json=payload)
        if (not isinstance(data.get("id"), str) or not data["id"].strip()
                or not isinstance(data.get("polling_url"), str)):
            raise BFLError("BFL response omitted the job ID or polling URL.")
        validate_polling_url(data["polling_url"])
        return data

    async def poll(self, polling_url: str) -> dict:
        return await self._request("GET", validate_polling_url(polling_url))
