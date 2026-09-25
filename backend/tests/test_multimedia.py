import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.api.multimedia import job_path, router, save_job
from backend.app.clients.bfl import BFLClient, BFLError, validate_polling_url
from backend.app.config import settings
from backend.app.state.multimedia import MultimediaRequest, build_payload

EXAMPLE = Path(__file__).resolve().parent / "fixtures/retinal-vein-occlusion.json"


def request_body():
    return {"original_prompt": "Compare a healthy eye and an eye with RVO side by side.",
            "verification": json.loads(EXAMPLE.read_text())}


class PayloadTests(unittest.TestCase):
    def test_actual_verifier_fixture_preserved(self):
        body = request_body()
        body["verification"]["explanation"] = "Show the impaired venous drainage."
        payload = build_payload(MultimediaRequest(**body))
        self.assertEqual(payload["mode"], "t2v")
        self.assertNotIn("keyframes", payload)
        for text in (body["original_prompt"], body["verification"]["context"],
                     body["verification"]["explanation"], body["verification"]["images"][0]["url"]):
            self.assertIn(text, payload["prompt"])

    def test_explicit_image_is_a_keyframe(self):
        body = request_body()
        body["opening_image_index"] = 2
        payload = build_payload(MultimediaRequest(**body))
        self.assertEqual(payload["mode"], "i2v")
        self.assertEqual(payload["keyframes"], body["verification"]["images"][2]["url"])

    def test_invalid_input(self):
        for update in ({"duration": 4}, {"duration": 21}, {"duration": 5.5},
                       {"original_prompt": " "}, {"opening_image_index": 40},
                       {"opening_image_index": True}, {"opening_image_index": "1"}):
            with self.subTest(update=update), self.assertRaises(ValidationError):
                MultimediaRequest(**(request_body() | update))

    def test_polling_url_boundary(self):
        for url in ("http://api.bfl.ai/result", "https://api.bfl.ai.evil.test/result",
                    "https://localhost/result", "https://user@api.bfl.ai/result",
                    "https://api.bfl.ai:bad/result"):
            with self.subTest(url=url), self.assertRaises(BFLError):
                validate_polling_url(url)
        self.assertEqual(validate_polling_url("https://api.us1.bfl.ai/result"), "https://api.us1.bfl.ai/result")


class ClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_submit_and_poll(self):
        def provider(request):
            self.assertEqual(request.headers["x-key"], "test-key")
            if request.method == "POST":
                self.assertEqual(request.url.path, "/v1/flux-3-video")
                return httpx.Response(200, json={"id": "provider-job", "polling_url": "https://api.bfl.ai/result"})
            return httpx.Response(200, json={"status": "Ready", "result": {"sample": "https://example.com/video.mp4"}})
        client = BFLClient("test-key", httpx.MockTransport(provider))
        submitted = await client.submit(build_payload(MultimediaRequest(**request_body())))
        self.assertEqual((await client.poll(submitted["polling_url"]))["status"], "Ready")

    async def test_missing_key_and_rate_limit(self):
        with self.assertRaises(BFLError) as error:
            await BFLClient("").submit({})
        self.assertEqual(error.exception.status_code, 503)
        client = BFLClient("test", httpx.MockTransport(lambda _: httpx.Response(429)))
        with self.assertRaisesRegex(BFLError, "rate limited"):
            await client.submit({})


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old = settings.cases_dir
        settings.cases_dir = Path(self.temp.name)
        app = FastAPI()
        app.include_router(router)
        self.client = TestClient(app)

    def tearDown(self):
        settings.cases_dir = self.old
        self.temp.cleanup()

    def test_preview_does_not_submit(self):
        with patch.object(BFLClient, "submit", new_callable=AsyncMock) as submit:
            self.assertEqual(self.client.post("/multimedia/preview", json=request_body()).status_code, 200)
            submit.assert_not_called()
        self.assertEqual(self.client.post("/multimedia", json={}).status_code, 422)

    def test_submit_poll_and_saved_result(self):
        with patch.object(BFLClient, "submit", new_callable=AsyncMock) as submit, patch.object(BFLClient, "poll", new_callable=AsyncMock) as poll:
            submit.return_value = {"id": "provider-job", "polling_url": "https://api.bfl.ai/result"}
            response = self.client.post("/multimedia", json=request_body())
            self.assertEqual(response.status_code, 202)
            job = response.json()
            self.assertNotIn("polling_url", job)
            poll.side_effect = [{"status": "Generating"}, {"status": "Ready", "result": {"sample": "https://example.com/clip.mp4"}}]
            path = f'/multimedia/{job["id"]}'
            self.assertEqual(self.client.get(path).json()["status"], "Generating")
            self.assertEqual(self.client.get(path).json()["sample_url"], "https://example.com/clip.mp4")
            self.assertEqual(self.client.get(path).json()["status"], "Ready")
            self.assertEqual(poll.await_count, 2)
            submit.assert_awaited_once()

    def test_moderation_and_missing_jobs(self):
        with patch.object(BFLClient, "submit", new_callable=AsyncMock) as submit, patch.object(BFLClient, "poll", new_callable=AsyncMock) as poll:
            submit.return_value = {"id": "p", "polling_url": "https://api.bfl.ai/result"}
            job = self.client.post("/multimedia", json=request_body()).json()
            poll.return_value = {"status": "Content Moderated"}
            response = self.client.get(f'/multimedia/{job["id"]}')
            self.assertEqual(response.json()["status"], "Content Moderated")
            self.assertIsNone(response.json()["sample_url"])
        self.assertEqual(self.client.get("/multimedia/invalid").status_code, 404)

    def test_invalid_provider_results_are_retryable_gateway_errors(self):
        with patch.object(BFLClient, "submit", new_callable=AsyncMock) as submit, patch.object(BFLClient, "poll", new_callable=AsyncMock) as poll:
            submit.return_value = {"id": "p", "polling_url": "https://api.bfl.ai/result"}
            job = self.client.post("/multimedia", json=request_body()).json()
            path = f'/multimedia/{job["id"]}'
            invalid_results = [{"status": []}, {"status": {"unexpected": True}},
                               {"status": "Ready", "result": []},
                               {"status": "Ready", "result": {"sample": "https:"}},
                               {"status": "Ready", "result": {"sample": "https://[invalid"}},
                               {"status": "Ready", "result": {"sample": "https://user:pass@example.com/video"}}]
            for result in invalid_results:
                with self.subTest(result=result):
                    poll.return_value = result
                    self.assertEqual(self.client.get(path).status_code, 502)
                    self.assertEqual(json.loads(job_path(job["id"]).read_text())["status"], "Pending")
            poll.return_value = {"status": "Ready", "result": {"sample": "https://example.com/clip.mp4"}}
            self.assertEqual(self.client.get(path).json()["status"], "Ready")

    def test_late_poll_does_not_overwrite_a_completed_job(self):
        with patch.object(BFLClient, "submit", new_callable=AsyncMock) as submit, patch.object(BFLClient, "poll", new_callable=AsyncMock) as poll:
            submit.return_value = {"id": "p", "polling_url": "https://api.bfl.ai/result"}
            job = self.client.post("/multimedia", json=request_body()).json()
            async def stale_poll(_):
                # Simulate a second poll completing while the first awaits BFL.
                path = job_path(job["id"])
                completed = json.loads(path.read_text())
                completed.update(status="Ready", sample_url="https://example.com/clip.mp4")
                save_job(path, completed)
                return {"status": "Generating"}
            poll.side_effect = stale_poll
            response = self.client.get(f'/multimedia/{job["id"]}')
            self.assertEqual(response.json()["status"], "Ready")
            self.assertEqual(json.loads(job_path(job["id"]).read_text())["status"], "Ready")


if __name__ == "__main__":
    unittest.main()
