import contextlib
import http.client
import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from tests import support  # noqa: F401
from tests.fake_backends import FakeBackend, ollama_chunk, ollama_reply
from agent_harness.app import build_app
from agent_harness.config import ConfigError
from agent_harness.interfaces import web
from agent_harness.locations import Locations

TOKEN = "t" * 32
CHUNKS = ["Hel", "lo ", "wor", "ld"]


def outcome(lines):
    """The final word on a reply from its stream: the last message, or the snapshot if it was already over."""
    last = lines[-1]
    if last["type"] == "snapshot":
        return {"type": last["state"], "error": last.get("error"), "summary": last.get("summary")}
    return last


class Reply:
    def __init__(self, status, body, headers):
        self.status, self.body, self.headers = status, body, headers


class Base(unittest.TestCase):
    def serve(self, *scripts, require_token=True, max_handlers=64, embedding_models=("embed:1",), log=None):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.fake = FakeBackend("ollama", models=("fake:1b", "embed:1"), scripts=list(scripts),
                                embedding_models=embedding_models)
        self.addCleanup(self.fake.stop)
        self.loc = Locations(Path(self.tmp.name))
        self.loc.ensure()
        self.loc.config_file.write_text(json.dumps({
            "token": TOKEN, "require_token": require_token, "host": "127.0.0.1",
            "backends": [{"id": "ol", "kind": "ollama", "url": self.fake.url}],
            "default_model": "ol:fake:1b", "memory": {"enabled": False},
            "timeouts": {"first_byte": 8, "idle": 8, "total": 30}}))
        self.app = build_app(self.loc)
        self.addCleanup(self.app.close)
        self.server = web.make_server(self.app, "127.0.0.1", 0, max_handlers=max_handlers, log=log)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.port = self.server.server_address[1]

    def conn(self):
        return http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)

    def call(self, method, path, body=None, token=TOKEN, headers=None):
        conn = self.conn()
        sent = dict(headers or {})
        if token is not None:
            sent["Authorization"] = f"Bearer {token}"
        data = None if body is None else (body if isinstance(body, bytes) else json.dumps(body).encode())
        if data is not None:
            sent["Content-Type"] = "application/json"
        conn.request(method, path, data, sent)
        resp = conn.getresponse()
        raw = resp.read()
        conn.close()
        try:
            parsed = json.loads(raw)
        except ValueError:
            parsed = raw.decode("utf-8", "replace")
        return Reply(resp.status, parsed, dict(resp.getheaders()))

    def stream(self, generation_id):
        conn = self.conn()
        conn.request("GET", f"/api/generations/{generation_id}/stream", headers={"Authorization": f"Bearer {TOKEN}"})
        resp = conn.getresponse()
        lines = [json.loads(line) for line in resp.read().decode().splitlines() if line.strip()]
        conn.close()
        return resp.status, lines

    def new_conversation(self):
        return self.call("POST", "/api/conversations", {}).body["id"]

    def send(self, conv, text="hi", model="ol:fake:1b", **kw):
        return self.call("POST", f"/api/conversations/{conv}/messages", {"text": text, "model": model}, **kw)


class AuthTests(Base):
    def test_every_api_route_demands_the_token(self):
        self.serve()
        for method, pattern, name in web.ROUTES:
            path = pattern.pattern.replace("(?P<id>[0-9a-f]+)", "0" * 32)
            with self.subTest(route=name):
                self.assertEqual(self.call(method, path, {} if method == "POST" else None, token=None).status, 401)
                self.assertEqual(self.call(method, path, {} if method == "POST" else None, token="x" * 32).status, 401)
                self.assertNotEqual(self.call(method, path, {} if method == "POST" else None).status, 401)

    def test_odd_authorization_headers_are_refused_not_crashes(self):
        self.serve()
        for header in ("Bearer", "Basic " + TOKEN, TOKEN, "Bearer " + TOKEN + "x", "Bearer ééé", "bearer"):
            with self.subTest(header=header):
                conn = self.conn()
                conn.putrequest("GET", "/api/models")
                conn.putheader("Authorization", header.encode("latin-1"))
                conn.endheaders()
                self.assertEqual(conn.getresponse().status, 401)
                conn.close()

    def test_unknown_api_paths_need_the_token_too(self):
        self.serve()
        self.assertEqual(self.call("GET", "/api/nothing", token=None).status, 401)
        self.assertEqual(self.call("GET", "/api/nothing").status, 404)
        self.assertEqual(self.call("DELETE", "/api/models").status, 501)  # method not supported at all

    def test_the_page_is_public_and_contains_no_secrets_or_innerhtml(self):
        self.serve()
        page = self.call("GET", "/", token=None)
        self.assertEqual(page.status, 200)
        self.assertIn("text/html", page.headers["Content-Type"])
        self.assertIn("<title>", page.body)
        self.assertNotIn(TOKEN, page.body)
        self.assertNotIn("innerHTML", page.body)  # model output is only ever shown as text
        self.assertIn("servedOverHttp", page.body)  # opened as a file, it explains itself
        for needed in ("showWindow", 'id="meter"', "Earlier messages are kept"):  # the context meter and marker
            self.assertIn(needed, page.body)
        for needed in ('autocapitalize="off"', "Show token", "#token="):  # friendly to phone keyboards and login links
            self.assertIn(needed, page.body)
        self.assertEqual(self.call("GET", "/elsewhere", token=None).status, 404)

    def test_the_server_refuses_to_start_with_a_weak_token_even_if_config_let_it_through(self):
        import dataclasses
        self.serve()
        for weak in ("", "short", "x" * 15):
            app = dataclasses.replace(self.app, config=dataclasses.replace(self.app.config, token=weak))
            with self.subTest(token=weak), self.assertRaisesRegex(ConfigError, "token"):
                web.make_server(app, "127.0.0.1", 0)

    def test_the_browsers_icon_request_is_answered_quietly_and_without_a_token(self):
        self.serve()
        self.assertEqual(self.call("GET", "/favicon.ico", token=None).status, 204)
        page = self.call("GET", "/", token=None).body
        self.assertIn('rel="icon"', page)  # and the page asks for no icon file at all
        self.assertIn('store.set("harness_conv", "")', page)  # a conversation that is gone is forgotten

    def test_with_the_token_switched_off_the_api_is_open(self):
        self.serve(require_token=False)
        self.assertEqual(self.call("GET", "/api/models", token=None).status, 200)

    def test_serving_an_open_api_beyond_this_machine_is_refused(self):
        with self.assertRaises(ConfigError):
            web.check_exposure("0.0.0.0", False)
        web.check_exposure("127.0.0.1", False)
        web.check_exposure("0.0.0.0", True)
        self.serve(require_token=False)
        with self.assertRaises(ConfigError):
            web.make_server(self.app.__class__(**{**self.app.__dict__, "config": self.app.config.__class__(
                **{**self.app.config.__dict__, "host": "0.0.0.0", "require_token": False})}), "0.0.0.0", 0)

    def test_the_token_never_reaches_the_output_or_a_response(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.serve(ollama_reply(CHUNKS))
            conv = self.new_conversation()
            self.send(conv)
            self.call("GET", "/api/models")
            self.call("GET", "/api/models", token="wrong" * 6)
            replies = [self.call("GET", "/api/conversations"), self.call("GET", f"/api/conversations/{conv}")]
        self.assertNotIn(TOKEN, out.getvalue() + err.getvalue())
        self.assertTrue(all(TOKEN not in json.dumps(r.body) for r in replies))


class RequestTests(Base):
    def test_bad_requests_get_clear_answers(self):
        self.serve()
        conv = self.new_conversation()
        path = f"/api/conversations/{conv}/messages"
        self.assertEqual(self.call("POST", path, b"{nope").status, 400)
        self.assertEqual(self.call("POST", path, b"[1]").status, 400)
        self.assertEqual(self.call("POST", path, {"text": "", "model": "ol:fake:1b"}).status, 400)
        self.assertEqual(self.call("POST", path, {"text": "x" * 20001, "model": "ol:fake:1b"}).status, 400)
        self.assertEqual(self.call("POST", path, {"text": "hi"}).status, 400)
        self.assertEqual(self.call("POST", path, {"text": "hi", "model": "nope:x"}).status, 400)
        self.assertEqual(self.call("POST", f"/api/conversations/{'0' * 32}/messages",
                                   {"text": "hi", "model": "ol:fake:1b"}).status, 404)
        self.assertEqual(self.call("GET", f"/api/conversations/{'0' * 32}").status, 404)
        self.assertEqual(self.call("GET", f"/api/generations/{'0' * 32}/stream").status, 404)
        self.assertEqual(self.fake.requests, [])  # none of that reached a model

    def test_oversized_and_unsized_bodies_are_refused_before_reading(self):
        self.serve()
        conv = self.new_conversation()
        for length, expected in (("2000000", 413), ("-5", 413), ("abc", 411)):
            conn = self.conn()
            conn.putrequest("POST", f"/api/conversations/{conv}/messages")
            conn.putheader("Authorization", f"Bearer {TOKEN}")
            conn.putheader("Content-Length", length)
            conn.endheaders()
            self.assertEqual(conn.getresponse().status, expected, length)
            conn.close()

    def test_models_lists_chat_models_and_marks_the_rest(self):
        self.serve()
        data = self.call("GET", "/api/models").body
        self.assertEqual(data["default"], "ol:fake:1b")
        self.assertEqual([(m["choice"], m["chat"], m["available"]) for m in data["models"]],
                         [("ol:embed:1", False, True), ("ol:fake:1b", True, True)])

    def test_the_handler_limit_answers_503_instead_of_piling_up(self):
        release = threading.Event()
        self.serve([("hold", release)] + ollama_reply(["A"]), ollama_reply(["B"]), max_handlers=2)
        a, b = self.new_conversation(), self.new_conversation()
        first = self.send(a).body["generation_id"]
        self.assertTrue(self.fake.request_seen.wait(5))
        second = self.send(b).body["generation_id"]
        held = []
        for gen in (first, second):  # two live streams use both handler slots
            conn = self.conn()
            conn.request("GET", f"/api/generations/{gen}/stream", headers={"Authorization": f"Bearer {TOKEN}"})
            resp = conn.getresponse()
            resp.readline()
            held.append(conn)
        self.assertEqual(self.call("GET", "/api/models").status, 503)
        release.set()
        for conn in held:
            conn.close()


class StreamEndTests(unittest.TestCase):
    def gen(self):
        from agent_harness.conversation.generation import Generation
        return Generation("g", "c", "ol:x")

    def test_a_normal_stream_ends_at_the_end_marker(self):
        gen = self.gen()
        snapshot, q = gen.subscribe()
        gen.publish({"type": "running"})
        gen.publish({"type": "delta", "text": "hi"})
        gen.publish({"type": "done", "summary": {}}, final=True)
        kinds = [m["type"] for m in web.stream_messages(gen, snapshot, q, poll=0.01)]
        self.assertEqual(kinds, ["snapshot", "running", "delta", "done"])

    def test_a_client_dropped_for_being_slow_still_gets_the_final_state_and_the_stream_ends(self):
        from agent_harness.conversation import generation
        with mock.patch.object(generation, "SUBSCRIBER_BUFFER", 2):
            gen = self.gen()
            snapshot, q = gen.subscribe()
        for word in ("a", "b", "c", "d", "e"):  # overflows the buffer, so this client is dropped
            gen.publish({"type": "delta", "text": word})
        gen.publish({"type": "done", "summary": {"stop_reason": "complete"}}, final=True)
        messages = list(web.stream_messages(gen, snapshot, q, ping_seconds=5, poll=0.01))
        self.assertEqual((messages[-1]["type"], messages[-1]["state"], messages[-1]["text"]), ("snapshot", "done", "abcde"))

    def test_a_quiet_wait_sends_pings_and_a_finished_reply_stops_them(self):
        gen = self.gen()
        snapshot, q = gen.subscribe()
        stream = web.stream_messages(gen, snapshot, q, ping_seconds=0.03, poll=0.01)
        self.assertEqual(next(stream)["type"], "snapshot")
        self.assertEqual(next(stream), {"type": "ping"})
        gen.publish({"type": "failed", "error": {"reason": "x", "message": "m", "partial_text": ""}}, final=True)
        self.assertEqual([m["type"] for m in stream][-1], "failed")

    def test_a_reply_that_is_already_over_is_one_snapshot(self):
        gen = self.gen()
        gen.publish({"type": "done", "summary": {}}, final=True)
        snapshot, q = gen.subscribe()
        self.assertEqual(len(list(web.stream_messages(gen, snapshot, q, poll=0.01))), 1)


class UnloadRouteTests(Base):
    def test_unload_frees_loaded_models_and_needs_the_token(self):
        self.serve()
        self.fake.loaded = ["fake:1b"]
        self.assertEqual(self.call("POST", "/api/unload", {}, token=None).status, 401)
        reply = self.call("POST", "/api/unload", {})
        self.assertEqual((reply.status, reply.body), (200, {"unloaded": {"ol": ["fake:1b"]}}))
        self.assertEqual(self.fake.unloaded[0]["keep_alive"], 0)

    def test_unload_is_refused_while_a_reply_is_in_progress(self):
        release = threading.Event()
        self.serve([("hold", release)] + ollama_reply(["A"]))
        self.fake.loaded = ["fake:1b"]
        conv = self.new_conversation()
        self.send(conv)
        self.assertTrue(self.fake.request_seen.wait(5))
        self.assertEqual(self.call("POST", "/api/unload", {}).status, 409)
        self.assertEqual(self.fake.unloaded, [])  # nothing was pulled out from under the reply
        release.set()


class ChatTests(Base):
    def test_a_full_chat_round_trip_over_http(self):
        self.serve(ollama_reply(CHUNKS))
        conv = self.new_conversation()
        accepted = self.send(conv, "Say hello", headers={"X-Client-Name": "phone"})
        self.assertEqual(accepted.status, 202)
        status, lines = self.stream(accepted.body["generation_id"])
        self.assertEqual((status, lines[0]["type"], outcome(lines)["type"]), (200, "snapshot", "done"))
        text = lines[0]["text"] + "".join(m["text"] for m in lines if m["type"] == "delta")
        self.assertEqual(text, "Hello world")
        got = self.call("GET", f"/api/conversations/{conv}").body
        self.assertEqual([(t["role"], t["text"]) for t in got["turns"]], [("user", "Say hello"), ("assistant", "Hello world")])
        self.assertEqual((got["window"]["sent"], got["window"]["dropped"]), (1, 0))  # what the reply was sent
        self.assertEqual(self.call("GET", "/api/conversations").body["conversations"][0]["title"], "Say hello")
        sent = self.fake.requests[0]["body"]
        self.assertEqual((sent["think"], sent["options"]["num_ctx"]), (False, 8192))
        user_event = [e for e in self.app.events.read() if e.kind == "turn.user"][0]
        self.assertEqual(user_event.payload["client"], "127.0.0.1 phone")

    def test_a_finished_reply_can_be_reattached_and_replays_its_outcome(self):
        self.serve(ollama_reply(CHUNKS))
        conv = self.new_conversation()
        gen = self.send(conv).body["generation_id"]
        self.stream(gen)
        status, lines = self.stream(gen)
        self.assertEqual((status, len(lines), lines[0]["state"], lines[0]["text"]), (200, 1, "done", "Hello world"))

    def test_a_second_send_while_answering_is_a_409(self):
        release = threading.Event()
        self.serve([("hold", release)] + ollama_reply(["A"]))
        conv = self.new_conversation()
        self.send(conv)
        self.assertTrue(self.fake.request_seen.wait(5))
        self.assertEqual(self.send(conv).status, 409)
        release.set()

    def test_a_client_that_disconnects_mid_stream_does_not_stop_the_reply(self):
        release = threading.Event()
        self.serve([ollama_chunk("Hel"), ("hold", release)] + ollama_reply(["lo"])[:-1] + [ollama_reply(["x"])[-1]])
        conv = self.new_conversation()
        gen_id = self.send(conv).body["generation_id"]
        conn = self.conn()
        conn.request("GET", f"/api/generations/{gen_id}/stream", headers={"Authorization": f"Bearer {TOKEN}"})
        resp = conn.getresponse()
        resp.readline()
        conn.close()  # the phone drops off
        release.set()
        self.assertTrue(self.app.runner.get(gen_id).finished.wait(5))
        turns = self.app.conversations.get(conv)["turns"]
        self.assertEqual([t["role"] for t in turns], ["user", "assistant"])
        self.assertEqual(turns[-1]["text"], "Hello")

    def test_a_failed_reply_is_reported_over_the_stream_and_the_conversation_stays_usable(self):
        self.serve([ollama_chunk("Hel"), ("reset",)], ollama_reply(["fine"]))
        conv = self.new_conversation()
        _status, lines = self.stream(self.send(conv).body["generation_id"])
        final = outcome(lines)
        self.assertEqual((final["type"], final["error"]["reason"], final["error"]["partial_text"]),
                         ("failed", "connection_reset", "Hel"))
        self.assertEqual(self.send(conv, "again").status, 202)

    def test_conversations_survive_a_restart(self):
        self.serve(ollama_reply(CHUNKS))
        conv = self.new_conversation()
        self.stream(self.send(conv, "remember me").body["generation_id"])
        self.app.close()
        again = build_app(self.loc)
        self.addCleanup(again.close)
        self.assertEqual([t["text"] for t in again.conversations.get(conv)["turns"]], ["remember me", "Hello world"])
        self.assertEqual(again.config.token, TOKEN)


if __name__ == "__main__":
    unittest.main()
