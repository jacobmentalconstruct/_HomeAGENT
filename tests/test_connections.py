import unittest

from tests import support  # noqa: F401
from tests.test_web import TOKEN, Base


class CleanCloseTests(Base):
    """A server that answers without reading the request body must not reset the connection under its answer."""

    def test_refusals_and_handlers_that_ignore_their_body_never_reset_the_connection(self):
        self.serve()
        body = b'{"text": "' + b"x" * 40000 + b'"}'
        cases = (
            ("POST", "/api/conversations", None, 401),    # refused before its body is read
            ("POST", "/api/conversations", "w" * 32, 401),  # a wrong token
            ("POST", "/api/conversations", TOKEN, 201),   # a handler that never looks at its body
            ("POST", "/api/unload", TOKEN, 200),          # another one
            ("POST", "/nowhere", None, 404),              # not an API path at all
            ("POST", "/api/nothing", TOKEN, 404),         # an unknown API path
        )
        for n in range(40):
            for method, path, token, expected in cases:
                reply = self.call(method, path, body, token=token)
                self.assertEqual(reply.status, expected, (n, method, path, token))

    def test_a_body_over_the_limit_is_still_refused_with_413(self):
        self.serve()
        conn = self.conn()
        conn.putrequest("POST", "/api/conversations")
        conn.putheader("Authorization", f"Bearer {TOKEN}")
        conn.putheader("Content-Length", "2000000")
        conn.endheaders()
        self.assertEqual(conn.getresponse().status, 413)
        conn.close()

    def test_a_post_without_a_length_is_treated_as_empty_where_no_body_is_needed(self):
        self.serve()
        for path, expected in (("/api/conversations", 201), ("/api/unload", 200)):
            conn = self.conn()
            conn.putrequest("POST", path)
            conn.putheader("Authorization", f"Bearer {TOKEN}")
            conn.endheaders()
            self.assertEqual(conn.getresponse().status, expected, path)
            conn.close()


if __name__ == "__main__":
    unittest.main()
