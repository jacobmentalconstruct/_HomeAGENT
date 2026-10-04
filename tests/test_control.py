import json
import shutil
import socket
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from tests import support
from tests.support import ROOT
from tests.fake_backends import FakeBackend
from tests.test_web import TOKEN, Base
from agent_harness.interfaces import control
from agent_harness.interfaces.control import (ServerProcess, TrafficStats, describe_loaded, describe_state,
                                              fetch_status, free_gpu, human_bytes, run_cli)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def python_command(code: str) -> list[str]:
    return [sys.executable, "-u", "-c", code]


class Collector:
    """Gathers the child's lines and lets a test wait for one without sleeping."""

    def __init__(self):
        self.lines, self._cond = [], threading.Condition()

    def __call__(self, line):
        with self._cond:
            self.lines.append(line)
            self._cond.notify_all()

    def wait_for(self, text, count=1, timeout=15):
        with self._cond:
            return self._cond.wait_for(lambda: sum(text in line for line in self.lines) >= count, timeout)


class ServerProcessTests(unittest.TestCase):
    def process(self, code):
        lines = Collector()
        proc = ServerProcess(ROOT, lines, python_command(code))
        self.addCleanup(proc.stop)
        return proc, lines

    def test_start_runs_the_command_passes_its_output_on_and_stop_ends_it(self):
        proc, lines = self.process("import time; print('hello', flush=True); time.sleep(60)")
        self.assertFalse(proc.running)
        self.assertTrue(proc.start())
        self.assertTrue(lines.wait_for("hello"))
        self.assertTrue(proc.running)
        self.assertFalse(proc.start())  # already running: nothing second is started
        self.assertTrue(proc.stop())
        self.assertFalse(proc.running)
        self.assertTrue(lines.wait_for("[server exited with code"))
        self.assertFalse(proc.stop())  # nothing left to stop

    def test_restart_starts_a_fresh_process(self):
        proc, lines = self.process("import os, time; print('pid', os.getpid(), flush=True); time.sleep(60)")
        proc.start()
        self.assertTrue(lines.wait_for("pid "))
        self.assertTrue(proc.restart())
        self.assertTrue(lines.wait_for("pid ", count=2))
        pids = {line.split()[1] for line in lines.lines if line.startswith("pid ")}
        self.assertEqual(len(pids), 2)  # a new process, not the old one kept going

    def test_a_server_that_exits_by_itself_is_noticed_with_its_exit_code(self):
        proc, lines = self.process("print('bye'); raise SystemExit(3)")
        proc.start()
        self.assertTrue(lines.wait_for("[server exited with code 3]"))
        self.assertFalse(proc.running)

    def test_stderr_is_part_of_the_output(self):
        proc, lines = self.process("import sys; print('oops', file=sys.stderr, flush=True)")
        proc.start()
        self.assertTrue(lines.wait_for("oops"))


class StatusClientTests(Base):
    def test_fetch_status_reads_the_servers_picture_and_tells_a_wrong_token_apart(self):
        self.serve()
        self.fake.loaded = ["fake:1b"]
        status = fetch_status("127.0.0.1", self.port, TOKEN)
        self.assertEqual((status["default_model"], status["replies_in_progress"]), ("ol:fake:1b", 0))
        self.assertEqual(describe_loaded(status), "fake:1b (5.0 GB)")
        self.assertEqual(fetch_status("127.0.0.1", self.port, "w" * 32), {"unauthorized": True})

    def test_nothing_listening_is_none_not_an_error(self):
        self.assertIsNone(fetch_status("127.0.0.1", free_port(), TOKEN))

    def test_free_gpu_asks_the_server_and_reports_a_refusal(self):
        self.serve()
        self.fake.loaded = ["fake:1b"]
        self.assertEqual(free_gpu("127.0.0.1", self.port, TOKEN), {"unloaded": {"ol": ["fake:1b"]}})
        self.assertEqual(free_gpu("127.0.0.1", self.port, "w" * 32), {"unauthorized": True})


class TrafficStatsTests(unittest.TestCase):
    def test_it_counts_the_last_minute_clients_and_failures(self):
        stats = TrafficStats()
        for second, line in ((0, "12:00:00 192.0.2.5 GET /api/models 200 4ms"),
                             (10, "12:00:10 192.0.2.5 POST /api/conversations 201 2ms"),
                             (20, "12:00:20 192.0.2.9 GET /api/models 401 1ms"),
                             (30, "12:00:30 198.51.100.7 GET /nowhere 404 1ms")):
            self.assertTrue(stats.add(line, now=second))
        self.assertEqual(stats.snapshot(now=40), {"last_minute": 4, "clients": 3, "errors": 2})
        self.assertEqual(stats.snapshot(now=75)["last_minute"], 2)  # the first two are over a minute old
        self.assertEqual(stats.snapshot(now=700), {"last_minute": 0, "clients": 0, "errors": 0})  # forgotten after ten minutes

    def test_lines_that_are_not_access_log_lines_are_ignored(self):
        stats = TrafficStats()
        for line in ("listening on 0.0.0.0:8765", "[server exited with code 0]", "", "token: run something",
                     "12:00:00 192.0.2.5 - - 503 busy"):
            stats.add(line, now=1)
        self.assertEqual(stats.snapshot(now=2)["last_minute"], 1)  # only the busy line is a request (a refusal)
        self.assertEqual(stats.snapshot(now=2)["errors"], 1)


class AddressTests(unittest.TestCase):
    def test_reach_host_uses_loopback_when_the_server_listens_everywhere(self):
        self.assertEqual([control.reach_host(h) for h in ("0.0.0.0", "", "127.0.0.1", "192.0.2.5")],
                         ["127.0.0.1", "127.0.0.1", "127.0.0.1", "192.0.2.5"])

    def test_the_main_network_address_comes_first_and_virtual_ones_after(self):
        from unittest import mock
        found = [(0, 0, 0, '', ('192.0.2.77', 0)), (0, 0, 0, '', ('198.51.100.9', 0)), (0, 0, 0, '', ('127.0.0.1', 0))]
        probe = mock.MagicMock()
        probe.__enter__.return_value = probe
        probe.getsockname.return_value = ('198.51.100.9', 5555)
        with mock.patch.object(control.socket, 'getaddrinfo', return_value=found), \
                mock.patch.object(control.socket, 'socket', return_value=probe):
            self.assertEqual(control.lan_addresses(), ['198.51.100.9', '192.0.2.77'])  # the main one first, not sorted by text
        probe.connect.side_effect = OSError('no route')
        with mock.patch.object(control.socket, 'getaddrinfo', return_value=found), \
                mock.patch.object(control.socket, 'socket', return_value=probe):
            self.assertEqual(control.lan_addresses(), ['192.0.2.77', '198.51.100.9'])  # falls back to the host's own list


class DescribeTests(unittest.TestCase):
    def test_human_bytes(self):
        self.assertEqual([human_bytes(n) for n in (0, 999, 1500, 8_800_000_000, 24_000_000_000)],
                         ["0 B", "999 B", "1.5 KB", "8.8 GB", "24.0 GB"])

    def test_describe_loaded_covers_models_nothing_and_a_backend_that_failed(self):
        self.assertEqual(describe_loaded({"loaded": {"ol": [{"name": "a:1", "size": 2_000_000_000}]}}), "a:1 (2.0 GB)")
        self.assertEqual(describe_loaded({"loaded": {"ol": []}}), "nothing")
        self.assertEqual(describe_loaded({"loaded": {"ol": "unreachable: no"}}), "ol: unreachable: no")
        self.assertEqual(describe_loaded(None), "unknown")

    def test_the_state_follows_whether_a_server_runs_and_answers(self):
        ok = {"uptime_seconds": 1}
        self.assertEqual(describe_state(True, ok)[0], "running")
        self.assertEqual(describe_state(True, None)[0], "starting")
        self.assertEqual(describe_state(False, None)[0], "stopped")
        self.assertEqual(describe_state(False, ok)[0], "outside")  # started by someone else
        self.assertEqual(describe_state(False, {"unauthorized": True})[0], "token")
        self.assertEqual(describe_state(True, {"error": "HTTP 500"})[0], "starting")


class TempRepo(unittest.TestCase):
    """A copy of the program with its own config, so the real server is started for real without touching yours."""

    def make_repo(self, **config):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        shutil.copy(ROOT / "harness.py", root / "harness.py")
        shutil.copytree(ROOT / "src", root / "src", ignore=shutil.ignore_patterns("__pycache__"))
        self.fake = FakeBackend("ollama", models=("fake:1b",), loaded=("fake:1b",))
        self.addCleanup(self.fake.stop)
        self.port = free_port()
        (root / "runtime").mkdir()
        (root / "runtime" / "config.json").write_text(json.dumps({
            "token": TOKEN, "host": "127.0.0.1", "port": self.port,
            "backends": [{"id": "ol", "kind": "ollama", "url": self.fake.url}], **config}))
        return root

    def wait_status(self, want_answer, timeout=25):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            status = fetch_status("127.0.0.1", self.port, TOKEN)
            if bool(status) == want_answer:
                return status
            time.sleep(0.2)
        self.fail(f"the server did not {'start answering' if want_answer else 'stop answering'}")


class RealServerTests(TempRepo):
    def test_the_real_server_starts_answers_restarts_and_stops_under_the_panels_control(self):
        root = self.make_repo()
        lines = Collector()
        proc = ServerProcess(root, lines)
        self.addCleanup(proc.stop)
        self.assertIsNone(fetch_status("127.0.0.1", self.port, TOKEN))
        proc.start()
        status = self.wait_status(True)
        self.assertEqual(describe_loaded(status), "fake:1b (5.0 GB)")
        self.assertTrue(lines.wait_for("listening on 127.0.0.1"))
        self.assertTrue(lines.wait_for("GET /api/status 200"))  # the panel's own question shows up in the traffic log
        stats = TrafficStats()
        for line in lines.lines:
            stats.add(line)
        self.assertGreaterEqual(stats.snapshot()["last_minute"], 1)
        proc.restart()
        self.wait_status(True)
        self.assertTrue(lines.wait_for("listening on 127.0.0.1", count=2))
        proc.stop()
        self.wait_status(False)

    def test_run_cli_runs_a_command_and_returns_what_it_printed(self):
        root = self.make_repo()
        self.assertIn(TOKEN, run_cli(root, "token"))
        self.assertIn("could not run", run_cli(root / "missing", "token"))


class PanelWindowTests(TempRepo):
    """Builds the real window, hidden, and drives it. Skipped where there is no display."""

    def setUp(self):
        try:
            import tkinter
            self.win = tkinter.Tk()
        except Exception as exc:  # noqa: BLE001 - no tkinter or no display
            self.skipTest(f"no window available: {exc}")
        self.win.withdraw()
        self.addCleanup(self._destroy_window)

    def _destroy_window(self):
        try:
            self.win.destroy()
        except Exception:  # noqa: BLE001
            pass

    def build(self, autostart=False, **config):
        from agent_harness.interfaces.gui import Panel
        root = self.make_repo(**config)
        self.panel = Panel(self.win, root, autostart=autostart)
        # registered after the temp folder's cleanup, so it runs first: the server must stop before its files go
        self.addCleanup(self.panel.shutdown)
        return self.panel

    def pump(self, until, timeout=30):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            self.win.update()
            if until():
                return True
            time.sleep(0.05)
        return False

    def test_the_panel_shows_what_the_server_reports_and_enables_the_right_buttons(self):
        panel = self.build()
        panel.apply({"uptime_seconds": 125, "replies_in_progress": 2, "loaded": {"ol": [{"name": "a:1", "size": 5_000_000_000}]}},
                    (4096, 16384))
        self.assertEqual(panel.state, "outside")  # a server answers but this panel did not start it
        self.assertEqual((panel.info["loaded"].cget("text"), panel.info["replies"].cget("text")), ("a:1 (5.0 GB)", "2"))
        self.assertEqual(panel.info["gpu"].cget("text"), "4.0 of 16.0 GB used")
        self.assertEqual(panel.info["uptime"].cget("text"), "2m 5s")
        panel.apply(None, None)
        self.assertEqual((panel.state, panel.info["gpu"].cget("text")), ("stopped", "not available"))
        self.assertFalse(panel.buttons["start"].instate(["disabled"]))
        self.assertTrue(panel.buttons["stop"].instate(["disabled"]))
        self.assertTrue(panel.buttons["restart"].instate(["disabled"]))

    def test_log_lines_land_in_the_window_failures_are_marked_and_counted(self):
        panel = self.build()
        for line in ("12:00:00 192.0.2.5 GET /api/models 200 3ms", "12:00:01 192.0.2.9 GET /api/models 401 1ms",
                     "listening on 127.0.0.1:1"):
            panel.lines.put(line)
        panel.drain_lines()
        text = panel.log.get("1.0", "end")
        self.assertIn("GET /api/models 401", text)
        self.assertIn("listening on", text)
        failed_ranges = panel.log.tag_ranges("failed")
        self.assertEqual(len(failed_ranges), 2)  # exactly one line is marked as failed
        panel.apply(None, None)
        self.assertEqual(panel.info["traffic"].cget("text"), "2 / 2 / 1")
        panel.clear_log()
        self.assertEqual(panel.log.get("1.0", "end").strip(), "")

    def test_the_log_keeps_only_the_most_recent_lines(self):
        from agent_harness.interfaces import gui
        panel = self.build()
        for i in range(gui.MAX_LINES + 300):
            panel.lines.put(f"line {i}")
        panel.drain_lines()
        lines = panel.log.get("1.0", "end").strip().splitlines()
        self.assertLessEqual(len(lines), gui.MAX_LINES)
        self.assertEqual(lines[-1], f"line {gui.MAX_LINES + 299}")

    def test_start_runs_the_real_server_and_stop_ends_it_through_the_window(self):
        panel = self.build(autostart=True)
        self.assertTrue(self.pump(lambda: panel.state == "running"), panel.log.get("1.0", "end"))
        self.assertIn("GET /api/status 200", panel.log.get("1.0", "end"))
        self.assertTrue(self.pump(lambda: panel.info["loaded"].cget("text") == "fake:1b (5.0 GB)"))
        self.assertTrue(panel.buttons["start"].instate(["disabled"]))
        panel.stop()
        self.assertTrue(self.pump(lambda: panel.state == "stopped"))
        panel.restart()
        self.assertTrue(self.pump(lambda: panel.state == "running"))

    def test_every_button_fits_in_the_window_at_its_default_width(self):
        panel = self.build()
        self.win.update_idletasks()
        needed = sum(b.winfo_reqwidth() + 4 for b in panel.buttons.values()) + 20
        self.assertLessEqual(needed, 860)  # the width the window opens at
        self.assertEqual(set(panel.buttons), {"start", "stop", "restart", "open", "link", "token", "gpu"})

    def test_the_phone_address_follows_the_configured_host(self):
        from unittest import mock
        status = {"uptime_seconds": 5, "replies_in_progress": 0, "loaded": {}}
        with mock.patch.object(control, "lan_addresses", return_value=["192.0.2.77"]):
            everywhere = self.build(host="0.0.0.0")
            everywhere.apply(status, None)
            self.assertEqual(everywhere.address.cget("text"), f"http://192.0.2.77:{self.port}/ (for your phone)")
            everywhere.copy_link()
            self.assertTrue(self.win.clipboard_get().startswith("http://192.0.2.77:"))
        everywhere.shutdown()
        local = self.build(host="127.0.0.1")
        local.apply(status, None)
        self.assertEqual(local.address.cget("text"), f"http://127.0.0.1:{self.port}/ (this computer only)")
        local.copy_link()
        self.assertTrue(self.win.clipboard_get().startswith("http://127.0.0.1:"))

    def test_copy_buttons_put_the_login_link_and_the_token_on_the_clipboard(self):
        panel = self.build()
        panel.copy_token()
        self.assertEqual(self.win.clipboard_get(), TOKEN)
        panel.copy_link()
        link = self.win.clipboard_get()
        self.assertTrue(link.startswith("http://") and link.endswith(f":{self.port}/#token={TOKEN}"), link)


if __name__ == "__main__":
    unittest.main()
