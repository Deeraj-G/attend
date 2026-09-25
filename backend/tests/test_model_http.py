import io
import json
import tempfile
import unittest
from pathlib import Path

import httpx
import numpy as np
import soundfile as sf
from pydantic import BaseModel

from backend.app.clients.lfm import LFMClient
from backend.app.clients.lfm_audio import TOKENS_PER_CHUNK, LFMAudioClient


class Answer(BaseModel):
    score: int


class LFMHttpTests(unittest.TestCase):
    def test_structured_completion_goes_to_llama_server(self):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json={"choices": [{"message": {"content": ' {"score": 4} '}}]})

        client = LFMClient(base_url="http://lfm:8080/", transport=httpx.MockTransport(handler))
        self.assertEqual(client.generate_structured("Rate it.", Answer).score, 4)

        self.assertEqual(str(requests[0].url), "http://lfm:8080/v1/chat/completions")
        body = json.loads(requests[0].content)
        self.assertEqual(body["temperature"], 0)
        self.assertEqual(body["max_tokens"], 4096)
        self.assertIn("JSON_SCHEMA", body["messages"][-1]["content"])
        self.assertIsNone(client.model)  # never loads weights in-process

    def test_server_error_raises(self):
        client = LFMClient(
            base_url="http://lfm:8080",
            transport=httpx.MockTransport(lambda request: httpx.Response(500)),
        )
        with self.assertRaises(httpx.HTTPStatusError):
            client.generate("Hi")


class LFMAudioHttpTests(unittest.TestCase):
    def test_transcribes_each_chunk_over_http(self):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json={"text": f" part {len(requests)} ", "tokens": 40})

        sample_rate = 16_000
        tone = 0.1 * np.sin(np.linspace(0, 2000 * np.pi, 45 * sample_rate)).astype("float32")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "recording.wav"
            sf.write(path, tone, sample_rate)
            client = LFMAudioClient(base_url="http://lfm-audio:8090", transport=httpx.MockTransport(handler))
            transcript = client.transcribe(path)

        self.assertEqual(transcript.text, "part 1 part 2")
        self.assertEqual(len(transcript.segments), 2)
        self.assertFalse(any(s.truncated for s in transcript.segments))
        self.assertEqual(requests[0].url.params["max_new_tokens"], str(TOKENS_PER_CHUNK))
        # Each request carries only its own chunk, as a readable WAV.
        body = requests[0].content
        wav = body[body.index(b"RIFF"):]
        samples, rate = sf.read(io.BytesIO(wav))
        self.assertEqual(rate, sample_rate)
        self.assertLessEqual(len(samples), 30 * sample_rate)


if __name__ == "__main__":
    unittest.main()
