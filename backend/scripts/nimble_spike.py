"""Day-1 Nimble spike: one text, one image and one video search.

Saves raw responses to backend/tests/fixtures/nimble/ and prints latency plus the
normalised results, so we can check the field names against the real API.

    python -m backend.scripts.nimble_spike "colonoscopy"
"""

import asyncio
import json
import sys
import time
from pathlib import Path

from backend.app.clients.nimble import VIDEO_DOMAINS, NimbleClient, _normalise_images, _normalise_search

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "nimble"


async def main(procedure: str) -> None:
    client = NimbleClient()
    FIXTURES.mkdir(parents=True, exist_ok=True)
    calls = [
        ("text", "/search", {"query": f"{procedure} what to expect", "max_results": 5}),
        ("image", "/serp", {"search_engine": "google_images", "query": f"{procedure} illustration", "num_results": 5, "country": "US"}),
        ("video", "/search", {"query": f"{procedure} patient education", "max_results": 5, "include_domains": VIDEO_DOMAINS}),
    ]
    for kind, path, payload in calls:
        start = time.perf_counter()
        try:
            raw = await client.raw(path, payload)
        except Exception as e:  # spike: show whatever went wrong and keep going
            print(f"[{kind}] FAILED after {time.perf_counter() - start:.1f}s: {e!r}")
            continue
        elapsed = time.perf_counter() - start
        (FIXTURES / f"{kind}.json").write_text(json.dumps(raw, indent=2))
        norm = _normalise_images(raw) if kind == "image" else _normalise_search(raw, kind)
        print(f"[{kind}] {elapsed:.1f}s, {len(norm)} normalised results (raw saved to fixtures/nimble/{kind}.json)")
        for r in norm[:3]:
            print(f"    {r['domain']:<25} {r['title'][:60]}")
        if not norm:
            print(f"    top-level keys: {list(raw)[:10]}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "colonoscopy"))
