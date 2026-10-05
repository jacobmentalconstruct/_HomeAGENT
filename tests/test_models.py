import json
import time
import unittest
from unittest import mock

from tests import support  # noqa: F401
from tests.fake_backends import (FakeBackend, llamacpp_chunk, llamacpp_reply, ollama_chunk,
                                 ollama_reply)
from agent_harness.config import BackendConfig, Timeouts
from agent_harness.models.errors import BackendError, UnknownModelChoice
from agent_harness.models.llamacpp import LlamaCppBackend
from agent_harness.models.ollama import OllamaBackend
from agent_harness.models.registry import ModelRegistry
from agent_harness.models.transport import Transport

FAST = Timeouts(connect=1, listing=0.6, first_byte=0.4, idle=0.3, total=1.2)
CHUNKS = ["Hel", "lo ", "wor", "ld"]
MESSAGES = [{"role": "user", "content": "hi"}]

PROTOCOLS = {
    "ollama": dict(cls=OllamaBackend, reply=ollama_reply, chunk=ollama_chunk,
                   error=("line", '{"error":"model crashed"}'), bad=("line", "{not json")),
    "llamacpp": dict(cls=LlamaCppBackend, reply=llamacpp_reply, chunk=llamacpp_chunk,
                     error=("raw", 'data: {"error":{"message":"boom"}}\n\n'), bad=("raw", "data: {oops\n\n")),
}


class Fakes(unittest.TestCase):
    def fake(self, kind, **kw):
        f = FakeBackend(kind, **kw)
        self.addCleanup(f.stop)
        return f

    def backend(self, kind, fake, timeouts=FAST, num_ctx=4096, cap=256, url=None):
        return PROTOCOLS[kind]["cls"](BackendConfig("b", kind, url or fake.url), Transport(timeouts), num_ctx, cap)

    def run_chat(self, kind, script, options=None, **kw):
        fake = self.fake(kind, scripts=[script])
        stream = self.backend(kind, fake, **kw).chat("m:1", MESSAGES, options)
        return fake, stream, list(stream)

    def failure(self, kind, script, **kw):
        fake = self.fake(kind, scripts=[script])
        stream = self.backend(kind, fake, **kw).chat("m:1", MESSAGES)
        with self.assertRaises(BackendError) as ctx:
            list(stream)
        return ctx.exception


class ReplyTests(Fakes):
    def test_reply_streams_chunks_that_match_the_script(self):
        for kind, p in PROTOCOLS.items():
            with self.subTest(kind=kind):
                _fake, stream, got = self.run_chat(kind, p["reply"](CHUNKS, prompt=11, evals=6))
                self.assertEqual(got, CHUNKS)
                self.assertEqual(stream.summary.text, "".join(CHUNKS))
                self.assertEqual((stream.chunks, stream.summary.stop_reason), (4, "complete"))
                self.assertEqual((stream.summary.prompt_tokens, stream.summary.reply_tokens), (11, 6))

    def test_length_marker_means_truncated(self):
        for kind, p in PROTOCOLS.items():
            with self.subTest(kind=kind):
                _fake, stream, _ = self.run_chat(kind, p["reply"](CHUNKS, done_reason="length"))
                self.assertEqual(stream.summary.stop_reason, "truncated")

    def test_missing_token_counts_are_none_not_an_error(self):
        for kind, p in PROTOCOLS.items():
            with self.subTest(kind=kind):
                _fake, stream, got = self.run_chat(kind, p["reply"](CHUNKS, prompt=None))
                self.assertEqual(got, CHUNKS)
                self.assertEqual((stream.summary.prompt_tokens, stream.summary.reply_tokens), (None, None))

    def test_llamacpp_ignores_comments_and_event_lines(self):
        script = [("raw", ": keepalive\n\n"), ("raw", "event: message\n")] + llamacpp_reply(["ok"])
        _fake, stream, got = self.run_chat("llamacpp", script)
        self.assertEqual((got, stream.summary.text), (["ok"], "ok"))


class FailureTests(Fakes):
    def test_error_object_inside_a_200_stream_is_protocol_error_with_partial_text(self):
        for kind, p in PROTOCOLS.items():
            with self.subTest(kind=kind):
                err = self.failure(kind, [p["chunk"]("Hel"), p["error"]])
                self.assertEqual((err.reason, err.partial_text), ("protocol_error", "Hel"))

    def test_malformed_line_is_protocol_error(self):
        for kind, p in PROTOCOLS.items():
            with self.subTest(kind=kind):
                err = self.failure(kind, [p["chunk"]("Hel"), p["bad"]])
                self.assertEqual((err.reason, err.partial_text), ("protocol_error", "Hel"))

    def test_llamacpp_error_field_line_is_protocol_error(self):
        err = self.failure("llamacpp", [llamacpp_chunk("Hel"), ("raw", 'error: {"message":"slot failed"}\n\n')])
        self.assertEqual((err.reason, err.partial_text), ("protocol_error", "Hel"))
        self.assertIn("slot failed", err.message)

    def test_end_of_stream_without_a_final_marker_is_incomplete_never_a_summary(self):
        for kind, p in PROTOCOLS.items():
            with self.subTest(kind=kind):
                fake = self.fake(kind, scripts=[[p["chunk"]("Hel"), p["chunk"]("lo")]])
                stream = self.backend(kind, fake).chat("m:1", MESSAGES)
                with self.assertRaises(BackendError) as ctx:
                    list(stream)
                self.assertEqual((ctx.exception.reason, ctx.exception.partial_text), ("incomplete", "Hello"))
                self.assertIsNone(stream.summary)

    def test_no_first_byte_times_out(self):
        for kind, p in PROTOCOLS.items():
            with self.subTest(kind=kind):
                err = self.failure(kind, [("sleep", 1.0)] + p["reply"](CHUNKS))
                self.assertEqual((err.reason, err.partial_text), ("timeout_first_byte", ""))

    def test_silence_after_some_chunks_times_out_idle(self):
        for kind, p in PROTOCOLS.items():
            with self.subTest(kind=kind):
                err = self.failure(kind, [p["chunk"]("Hel"), ("sleep", 0.9)] + p["reply"](CHUNKS))
                self.assertEqual((err.reason, err.partial_text), ("timeout_idle", "Hel"))

    def test_endless_output_stops_at_the_total_deadline(self):
        short = Timeouts(connect=1, listing=1, first_byte=0.5, idle=0.5, total=0.5)
        for kind, p in PROTOCOLS.items():
            with self.subTest(kind=kind):
                started = time.monotonic()
                err = self.failure(kind, [("endless", p["chunk"]("x")[1] + ("\n" if kind == "ollama" else ""), 0.05)],
                                   timeouts=short)
                self.assertEqual(err.reason, "deadline")
                self.assertTrue(err.partial_text.startswith("x"))
                self.assertLess(time.monotonic() - started, 2.5)

    def test_connection_dropped_mid_body_is_connection_reset(self):
        for kind, p in PROTOCOLS.items():
            with self.subTest(kind=kind):
                err = self.failure(kind, [p["chunk"]("Hel"), ("reset",)])
                self.assertEqual((err.reason, err.partial_text), ("connection_reset", "Hel"))

    def test_refused_connection_is_unreachable(self):
        # Windows takes about 2 s to refuse a loopback connection, so allow the connect longer.
        patient = Timeouts(connect=5, listing=5, first_byte=1, idle=1, total=5)
        fake = self.fake("ollama")
        url = fake.url
        fake.stop()
        stream = self.backend("ollama", fake, timeouts=patient, url=url).chat("m:1", MESSAGES)
        with self.assertRaises(BackendError) as ctx:
            list(stream)
        self.assertEqual(ctx.exception.reason, "unreachable")

    def test_connect_timeout_maps_to_timeout_connect(self):
        # A loopback fake cannot honestly stall a connect, so the transport's mapping is exercised
        # by making the connect call itself time out.
        for kind in PROTOCOLS:
            with self.subTest(kind=kind), mock.patch("http.client.HTTPConnection.connect",
                                                      side_effect=TimeoutError):
                with self.assertRaises(BackendError) as ctx:
                    list(self.backend(kind, self.fake(kind)).chat("m:1", MESSAGES))
                self.assertEqual(ctx.exception.reason, "timeout_connect")

    def test_a_clean_end_without_the_final_marker_is_not_a_reset(self):
        err = self.failure("ollama", [ollama_chunk("Hel")])
        self.assertEqual(err.reason, "incomplete")

    def test_http_errors_keep_status_and_server_text(self):
        for kind in PROTOCOLS:
            with self.subTest(kind=kind):
                err = self.failure(kind, [("status", 500, "backend exploded")])
                self.assertEqual((err.reason, err.status, err.detail), ("http_error", 500, "backend exploded"))
                self.assertIn("500", err.message)

    def test_context_overflow_400_is_classified_only_for_recognized_backend_errors(self):
        body = "the request exceeds the available context size"
        self.assertEqual(self.failure("llamacpp", [("status", 400, body)]).reason, "context_exceeded")
        self.assertEqual(self.failure("llamacpp", [("status", 400, "bad json")]).reason, "http_error")
        self.assertEqual(self.failure("ollama", [("status", 400, "the input length exceeds the context length")]).reason,
                         "context_exceeded")
        self.assertEqual(self.failure("ollama", [("status", 400, "bad json")]).reason, "http_error")


class RequestTests(Fakes):
    def test_generation_deadline_is_shared_with_the_backend_transport(self):
        fake = self.fake("ollama")
        stream = self.backend("ollama", fake).chat("m:1", MESSAGES,
                                                   deadline=time.monotonic() - 1)
        with self.assertRaises(BackendError) as caught:
            list(stream)
        self.assertEqual(caught.exception.reason, "deadline")
        self.assertEqual(fake.requests, [])

    def test_ollama_request_carries_num_ctx_and_the_reply_cap(self):
        fake, _s, _ = self.run_chat("ollama", ollama_reply(CHUNKS), num_ctx=4096, cap=256)
        sent = fake.requests[0]
        self.assertEqual((sent["path"], sent["body"]["model"], sent["body"]["messages"], sent["body"]["stream"]),
                         ("/api/chat", "m:1", MESSAGES, True))
        self.assertIs(sent["body"]["truncate"], False)
        self.assertEqual(sent["body"]["options"], {"num_ctx": 4096, "num_predict": 256})

    def test_llamacpp_request_has_no_num_ctx_and_asks_for_usage(self):
        fake, _s, _ = self.run_chat("llamacpp", llamacpp_reply(CHUNKS), num_ctx=4096, cap=256)
        sent = fake.requests[0]
        self.assertEqual(sent["path"], "/v1/chat/completions")
        self.assertNotIn("num_ctx", json.dumps(sent["body"]))
        self.assertEqual((sent["body"]["max_tokens"], sent["body"]["stream_options"]),
                         (256, {"include_usage": True}))

    def test_options_override_the_cap_and_pass_temperature(self):
        opts = {"max_reply_tokens": 7, "temperature": 0}
        fake, _s, _ = self.run_chat("ollama", ollama_reply(CHUNKS), options=opts)
        self.assertEqual(fake.requests[0]["body"]["options"], {"num_ctx": 4096, "num_predict": 7, "temperature": 0})
        fake, _s, _ = self.run_chat("llamacpp", llamacpp_reply(CHUNKS), options=opts)
        body = fake.requests[0]["body"]
        self.assertEqual((body["max_tokens"], body["temperature"]), (7, 0))

    def test_thinking_is_off_unless_asked_for(self):
        fake, _s, _ = self.run_chat("ollama", ollama_reply(CHUNKS))
        self.assertIs(fake.requests[0]["body"]["think"], False)
        fake, _s, _ = self.run_chat("ollama", ollama_reply(CHUNKS), options={"think": True})
        self.assertIs(fake.requests[0]["body"]["think"], True)

    def test_closing_the_stream_early_drops_the_connection(self):
        for kind, p in PROTOCOLS.items():
            with self.subTest(kind=kind):
                fake = self.fake(kind, scripts=[[("endless", p["chunk"]("x")[1] + ("\n" if kind == "ollama" else ""), 0.02)]])
                stream = self.backend(kind, fake, timeouts=Timeouts(1, 1, 1, 1, 30)).chat("m:1", MESSAGES)
                it = iter(stream)
                for _ in range(3):
                    next(it)
                it.close()
                self.assertTrue(fake.client_gone.wait(3), "the server never saw the client leave")


class ErrorTests(unittest.TestCase):
    def test_every_declared_reason_is_accepted_and_a_typo_is_not(self):
        from agent_harness.models.errors import REASONS
        for reason in REASONS:
            self.assertEqual(BackendError(reason, "m").reason, reason)
        with self.assertRaises(ValueError):
            BackendError("timeout_idel", "typo")


class UnloadTests(Fakes):
    def test_ollama_unload_asks_each_loaded_model_to_leave_memory(self):
        fake = self.fake("ollama", loaded=("big:9b", "small:1b"))
        released = self.backend("ollama", fake).unload_all()
        self.assertEqual(released, ["big:9b", "small:1b"])
        self.assertEqual([(r["model"], r["keep_alive"]) for r in fake.unloaded], [("big:9b", 0), ("small:1b", 0)])
        self.assertEqual(self.backend("ollama", fake).unload_all(), [])  # nothing left to free

    def test_one_model_that_will_not_unload_does_not_leave_the_others_in_memory(self):
        fake = self.fake("ollama", loaded=("stuck:1b", "big:9b"), unload_fails=("stuck:1b",))
        self.assertEqual(self.backend("ollama", fake).unload_all(), ["big:9b"])

    def test_llamacpp_cannot_unload_and_says_so_by_returning_nothing(self):
        self.assertEqual(self.backend("llamacpp", self.fake("llamacpp")).unload_all(), [])

    def test_chat_asks_ollama_to_keep_the_model_for_the_configured_time(self):
        fake = self.fake("ollama", scripts=[ollama_reply(CHUNKS)])
        list(self.backend("ollama", fake).chat("m:1", MESSAGES))
        self.assertEqual(fake.requests[0]["body"]["keep_alive"], "3m")
        fake = self.fake("ollama", scripts=[ollama_reply(CHUNKS)])
        backend = OllamaBackend(BackendConfig("b", "ollama", fake.url), Transport(FAST), 4096, 256, keep_alive="45s")
        list(backend.chat("m:1", MESSAGES))
        self.assertEqual(fake.requests[0]["body"]["keep_alive"], "45s")

    def test_registry_unload_reports_each_backend_and_a_failure_as_text(self):
        dead = self.fake("llamacpp")
        dead.stop()
        patient = Timeouts(connect=5, listing=5, first_byte=1, idle=1, total=5)
        busy = self.fake("ollama", loaded=("big:9b",))
        ollama_down = self.fake("ollama")
        ollama_down.stop()
        adapters = [OllamaBackend(BackendConfig("ok", "ollama", busy.url), Transport(patient), 4096, 256),
                    OllamaBackend(BackendConfig("gone", "ollama", ollama_down.url), Transport(patient), 4096, 256)]
        result = ModelRegistry(adapters).unload_all()
        self.assertEqual(result["ok"], ["big:9b"])
        self.assertTrue(result["gone"].startswith("unreachable"))


class ListingTests(Fakes):
    def test_ollama_embedding_endpoint_returns_validated_vectors(self):
        fake = self.fake("ollama")
        backend = self.backend("ollama", fake)
        vectors = backend.embed("nomic-embed-text", ["Where do I live?", "My office has a blue door."])
        self.assertEqual(vectors, [[1.0, 0.0], [0.0, 1.0]])

    def test_ollama_embedding_rejects_non_finite_vectors(self):
        backend = self.backend("ollama", self.fake("ollama"))
        with mock.patch.object(backend.transport, "post_json", return_value={"embeddings": [[float("nan")]]}):
            with self.assertRaises(BackendError):
                backend.embed("nomic-embed-text", ["test"])

    def test_each_protocol_lists_sorted_models(self):
        for kind in PROTOCOLS:
            with self.subTest(kind=kind):
                fake = self.fake(kind, models=("b:2", "a:1"))
                self.assertEqual(self.backend(kind, fake).list_models(), ["a:1", "b:2"])

    def test_embedding_models_are_marked_not_chat(self):
        fake = self.fake("ollama", models=("chat:1", "embed:1"), embedding_models=("embed:1",))
        entries = ModelRegistry([self.backend("ollama", fake)]).list_models()
        self.assertEqual([(e.choice, e.chat) for e in entries], [("b:chat:1", True), ("b:embed:1", False)])

    def test_llamacpp_models_count_as_chat_and_unknown_capabilities_count_as_chat(self):
        fake = self.fake("llamacpp", models=("gguf",))
        self.assertTrue(self.backend("llamacpp", fake).is_chat("gguf"))
        broken = self.fake("ollama", models=("x:1",))
        backend = self.backend("ollama", broken)
        broken.stop()  # /api/show cannot be reached, so the capability is unknown
        self.assertTrue(backend.is_chat("x:1"))

    def test_models_are_checked_for_chat_capability_side_by_side(self):
        names = tuple(f"m{i}:1b" for i in range(8))
        fake = self.fake("ollama", models=names, show_delay=0.4, embedding_models=("m3:1b",))
        patient = Timeouts(connect=5, listing=5, first_byte=2, idle=2, total=5)
        registry = ModelRegistry([OllamaBackend(BackendConfig("b", "ollama", fake.url), Transport(patient), 4096, 256)])
        started = time.monotonic()
        entries = registry.list_models()
        self.assertLess(time.monotonic() - started, 1.6)  # one at a time would take 3.2 seconds
        self.assertEqual([e.chat for e in entries], [n != "m3:1b" for n in names])  # answers stay with the right model

    def test_wrong_shapes_and_non_json_are_protocol_errors(self):
        for kind in PROTOCOLS:
            for body in ({"unexpected": 1}, b"not json at all"):
                with self.subTest(kind=kind, body=body), self.assertRaises(BackendError) as ctx:
                    self.backend(kind, self.fake(kind, list_body=body)).list_models()
                self.assertEqual(ctx.exception.reason, "protocol_error")

    def registry(self, timeouts=FAST, **backends):
        adapters = []
        transport = Transport(timeouts)
        for ident, (kind, fake) in backends.items():
            adapters.append(PROTOCOLS[kind]["cls"](BackendConfig(ident, kind, fake.url), transport, 4096, 256))
        return ModelRegistry(adapters)

    def test_registry_lists_both_backends_as_backend_id_model(self):
        reg = self.registry(ol=("ollama", self.fake("ollama", models=("phi3:mini-128k", "x:1"))),
                            cpp=("llamacpp", self.fake("llamacpp", models=("gguf",))))
        entries = reg.list_models()
        self.assertEqual([e.choice for e in entries], ["ol:phi3:mini-128k", "ol:x:1", "cpp:gguf"])
        self.assertTrue(all(e.available for e in entries))

    def test_a_downed_backend_is_an_entry_not_a_gap(self):
        dead = self.fake("llamacpp")
        dead.stop()
        patient = Timeouts(connect=5, listing=5, first_byte=1, idle=1, total=5)  # see the refusal note above
        reg = self.registry(patient, ol=("ollama", self.fake("ollama", models=("x:1",))), cpp=("llamacpp", dead))
        entries = reg.list_models()
        down = [e for e in entries if not e.available]
        self.assertEqual([(e.backend_id, e.reason, e.choice) for e in down], [("cpp", "unreachable", None)])
        self.assertEqual([e.choice for e in entries if e.available], ["ol:x:1"])

    def test_a_backend_that_never_answers_times_out_while_the_other_still_lists(self):
        hung = self.fake("llamacpp", list_delay=5)
        reg = self.registry(ol=("ollama", self.fake("ollama", models=("x:1",))), cpp=("llamacpp", hung))
        started = time.monotonic()
        entries = reg.list_models()
        self.assertLess(time.monotonic() - started, FAST.listing + 0.8)
        self.assertEqual([(e.backend_id, e.reason) for e in entries if not e.available], [("cpp", "timeout_listing")])
        self.assertEqual([e.choice for e in entries if e.available], ["ol:x:1"])

    def test_backends_are_listed_in_parallel_not_one_after_another(self):
        reg = self.registry(a=("ollama", self.fake("ollama", list_delay=5)),
                            b=("llamacpp", self.fake("llamacpp", list_delay=5)))
        started = time.monotonic()
        entries = reg.list_models()
        self.assertLess(time.monotonic() - started, FAST.listing * 1.6)  # sequential would be about 2x
        self.assertEqual([e.reason for e in entries], ["timeout_listing", "timeout_listing"])

    def test_an_unusable_url_that_slipped_past_config_fails_one_backend_not_the_listing(self):
        for bad in ("http://127.0.0.1:99999", "http://127.0.0.1:abc", "http://ho st:1"):
            with self.subTest(url=bad):
                broken = OllamaBackend(BackendConfig("bad", "ollama", bad), Transport(FAST), 4096, 256)
                good = PROTOCOLS["ollama"]["cls"](BackendConfig("ol", "ollama", self.fake("ollama", models=("x:1",)).url),
                                                  Transport(FAST), 4096, 256)
                entries = ModelRegistry([broken, good]).list_models()
                self.assertEqual([(e.backend_id, e.reason) for e in entries if not e.available], [("bad", "unreachable")])
                self.assertEqual([e.choice for e in entries if e.available], ["ol:x:1"])

    def test_resolve_splits_on_the_first_colon_only(self):
        reg = self.registry(ol=("ollama", self.fake("ollama")))
        backend, model = reg.resolve("ol:phi3:mini-128k")
        self.assertEqual((backend.config.id, model), ("ol", "phi3:mini-128k"))

    def test_resolve_refuses_unknown_ids_and_malformed_choices(self):
        reg = self.registry(ol=("ollama", self.fake("ollama")))
        for choice in ("nope:x", "ol", "ol:", ":x", ""):
            with self.subTest(choice=choice), self.assertRaises(UnknownModelChoice):
                reg.resolve(choice)

    def test_registry_with_no_backends_lists_nothing(self):
        self.assertEqual(ModelRegistry([]).list_models(), [])


if __name__ == "__main__":
    unittest.main()
