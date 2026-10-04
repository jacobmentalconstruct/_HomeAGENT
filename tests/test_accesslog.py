import contextlib
import io
import re
import unittest

from tests import support  # noqa: F401
from tests.fake_backends import ollama_reply
from tests.test_web import CHUNKS, TOKEN, Base
from agent_harness.interfaces import web


class AccessLogTests(Base):
    def test_each_request_is_one_line_with_who_what_status_and_time(self):
        lines = []
        self.serve(ollama_reply(CHUNKS), log=lines.append)
        self.call("GET", "/api/models")
        self.call("GET", "/api/models", token=None)
        self.call("GET", "/api/nothing")
        conv = self.new_conversation()
        gen = self.send(conv, "a private message").body["generation_id"]
        self.stream(gen)
        self.call("GET", "/")
        pattern = r"^[0-9]{2}:[0-9]{2}:[0-9]{2} 127[.]0[.]0[.]1 (GET|POST) [^ ]+ [0-9]{3} [0-9]+ms$"
        self.assertTrue(all(re.match(pattern, line) for line in lines), lines)
        shown = [" ".join(line.split()[2:5]) for line in lines]
        self.assertEqual(shown[:3], ["GET /api/models 200", "GET /api/models 401", "GET /api/nothing 404"])
        self.assertIn("POST /api/conversations 201", shown)
        self.assertIn(f"GET /api/generations/{gen}/stream 200", shown)
        self.assertIn("GET / 200", shown)

    def test_the_log_never_holds_the_token_a_query_string_or_message_text(self):
        lines = []
        self.serve(ollama_reply(CHUNKS), log=lines.append)
        conv = self.new_conversation()
        self.send(conv, "very private words")
        self.call("GET", f"/api/models?token={TOKEN}&x=secret")
        text = "\n".join(lines)
        self.assertNotIn(TOKEN, text)
        self.assertNotIn("secret", text)
        self.assertNotIn("very private words", text)
        self.assertIn("GET /api/models 200", text)

    def test_the_logged_path_is_sanitised_and_bounded(self):
        self.assertEqual(web.log_path("/api/x?token=abc"), "/api/x")
        self.assertEqual(web.log_path("/a\r\nFAKE 200 line\x00"), "/a??FAKE 200 line?")  # no forged log lines
        self.assertEqual(len(web.log_path("/" + "x" * 500)), 120)

    def test_a_malformed_request_still_gets_an_answer_and_a_log_line_with_no_terminal_codes(self):
        import socket
        lines = []
        self.serve(log=lines.append)
        for raw in (b"GARBAGE\r\n\r\n", b"GET /api/models HTTP/9.9\r\n\r\n",
                    bytes([27]) + b"[2JPUT /api/models HTTP/1.1\r\n\r\n"):
            with socket.create_connection(("127.0.0.1", self.port), timeout=5) as sock:
                sock.sendall(raw)
                answer = sock.recv(200)
                self.assertTrue(answer, raw)  # answered, not dropped (a request that cannot be parsed gets a bare body)
                if raw.startswith(bytes([27])):  # a well-formed request with an odd method gets a real status line
                    self.assertTrue(answer.startswith(b"HTTP/"), raw)
        self.assertEqual(self.call("GET", "/api/models").status, 200)  # and the server carries on
        text = "".join(lines)
        self.assertTrue(all(32 <= ord(ch) < 127 or ch == chr(10) for ch in text), repr(text))  # nothing but printable
        self.assertNotIn(chr(27), text)

    def test_without_a_log_nothing_is_printed(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.serve()
            self.call("GET", "/api/models")
        self.assertEqual(out.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
