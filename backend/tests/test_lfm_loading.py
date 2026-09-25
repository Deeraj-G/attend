import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.app.clients.lfm import LFMClient


class LoadingTests(unittest.TestCase):
    def test_concurrent_first_calls_load_one_complete_pair(self):
        entered, release, second_started = Event(), Event(), Event()
        model, tokenizer = object(), object()

        def load_model(*args, **kwargs):
            entered.set()
            if not release.wait(5):
                raise TimeoutError("Test did not release model loading")
            return model

        model_factory = Mock(side_effect=load_model)
        tokenizer_factory = Mock(return_value=tokenizer)
        transformers = SimpleNamespace(
            AutoModelForCausalLM=SimpleNamespace(from_pretrained=model_factory),
            AutoTokenizer=SimpleNamespace(from_pretrained=tokenizer_factory),
        )
        client = LFMClient()

        def second_load():
            second_started.set()
            client._load()

        with patch.dict(sys.modules, {"transformers": transformers}), ThreadPoolExecutor(2) as pool:
            first = pool.submit(client._load)
            try:
                self.assertTrue(entered.wait(5))
                second = pool.submit(second_load)
                self.assertTrue(second_started.wait(5))
                self.assertIsNone(client.model)
                self.assertIsNone(client.tokenizer)
            finally:
                release.set()
            first.result(timeout=5)
            second.result(timeout=5)
        model_factory.assert_called_once()
        tokenizer_factory.assert_called_once()
        self.assertIs(client.model, model)
        self.assertIs(client.tokenizer, tokenizer)

    def test_failed_tokenizer_load_does_not_publish_partial_pair_and_can_retry(self):
        model, tokenizer = object(), object()
        transformers = SimpleNamespace(
            AutoModelForCausalLM=SimpleNamespace(from_pretrained=Mock(return_value=model)),
            AutoTokenizer=SimpleNamespace(from_pretrained=Mock(
                side_effect=[RuntimeError("load failed"), tokenizer]
            )),
        )
        client = LFMClient()
        with patch.dict(sys.modules, {"transformers": transformers}):
            with self.assertRaisesRegex(RuntimeError, "load failed"):
                client._load()
            self.assertIsNone(client.model)
            self.assertIsNone(client.tokenizer)
            client._load()
        self.assertIs(client.model, model)
        self.assertIs(client.tokenizer, tokenizer)
