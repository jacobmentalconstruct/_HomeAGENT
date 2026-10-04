"""The control panel window: start, stop and restart the server, open the page, free the GPU, watch traffic.

A thin view over control.py. It holds no domain logic and never opens the database."""

from __future__ import annotations

import queue
import re
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox, ttk

from ..config import ConfigError, load_config
from ..locations import Locations, repo_locations
from . import control

MAX_LINES = 2000
POLL_SECONDS = 2.0
COLOURS = {"running": "#2e9e4f", "starting": "#d99a00", "stopped": "#c0392b", "outside": "#2f6fd0", "token": "#c0392b"}
_FAILED_LINE = re.compile(r" [45][0-9]{2} ")


class Panel:
    def __init__(self, win: tk.Tk, root: Path, autostart: bool = True):
        self.win, self.root, self.locations = win, root, Locations(root)
        self.lines: queue.Queue[str] = queue.Queue()
        self.results: queue.Queue[dict] = queue.Queue()
        self.notes: queue.Queue[str] = queue.Queue()  # messages from worker threads; only this window's thread shows them
        self.stats = control.TrafficStats()
        self.server = control.ServerProcess(root, self.lines.put)
        self.status: dict | None = None
        self.state = "stopped"
        self._quit = threading.Event()
        self._build()
        win.protocol("WM_DELETE_WINDOW", self.close)
        self._poll = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll.start()
        self._tick_id = win.after(150, self._tick)
        if autostart:
            self.start()

    # -- layout ---------------------------------------------------------------

    def _build(self) -> None:
        w = self.win
        w.title("_HomeAGENT")
        w.geometry("860x600")
        w.minsize(660, 440)
        top = ttk.Frame(w, padding=(10, 8))
        top.pack(fill="x")
        self.dot = tk.Label(top, text="●", font=("Segoe UI", 18))
        self.dot.pack(side="left")
        self.state_text = ttk.Label(top, text="Stopped", font=("Segoe UI", 12, "bold"))
        self.state_text.pack(side="left", padx=6)
        self.address = ttk.Label(top, text="")
        self.address.pack(side="left", padx=14)
        bar = ttk.Frame(w, padding=(10, 0))
        bar.pack(fill="x")
        self.buttons: dict[str, ttk.Button] = {}
        for key, label, command in (("start", "Start", self.start), ("stop", "Stop", self.stop),
                                    ("restart", "Restart", self.restart), ("open", "Open page", self.open_page),
                                    ("link", "Copy phone link", self.copy_link), ("token", "Copy token", self.copy_token),
                                    ("gpu", "Free GPU", self.free_gpu)):
            self.buttons[key] = ttk.Button(bar, text=label, command=command)
            self.buttons[key].pack(side="left", padx=2, pady=6)
        info = ttk.LabelFrame(w, text="Now", padding=8)
        info.pack(fill="x", padx=10, pady=4)
        self.info: dict[str, ttk.Label] = {}
        for row, (key, label) in enumerate((("loaded", "Models in memory"), ("gpu", "GPU memory"),
                                            ("replies", "Replies in progress"),
                                            ("traffic", "Requests (last minute, clients, failed)"),
                                            ("uptime", "Server uptime"))):
            ttk.Label(info, text=label + ":").grid(row=row, column=0, sticky="w")
            self.info[key] = ttk.Label(info, text="-")
            self.info[key].grid(row=row, column=1, sticky="w", padx=10)
        head = ttk.Frame(w, padding=(10, 4, 10, 0))
        head.pack(fill="x")
        ttk.Label(head, text="Server output and traffic").pack(side="left")
        ttk.Button(head, text="Clear", command=self.clear_log).pack(side="right")
        self.follow = tk.BooleanVar(value=True)
        ttk.Checkbutton(head, text="Follow", variable=self.follow).pack(side="right", padx=8)
        body = ttk.Frame(w, padding=(10, 4))
        body.pack(fill="both", expand=True)
        self.log = tk.Text(body, height=10, wrap="none", state="disabled", font=("Consolas", 9))
        scroll = ttk.Scrollbar(body, command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.log.pack(side="left", fill="both", expand=True)
        self.log.tag_configure("failed", foreground="#c0392b")
        self.log.tag_configure("system", foreground="#6b6b6b")
        self.note = ttk.Label(w, text="", padding=(10, 3))
        self.note.pack(fill="x")

    # -- settings and messages --------------------------------------------------

    def _settings(self) -> tuple[int, str, str] | None:
        """The port and token from the config file, read fresh each time so a changed token is picked up."""
        try:
            config = load_config(self.locations.config_file)
        except ConfigError as exc:
            self.say(f"Config problem: {exc}")
            return None
        return config.port, config.token, config.host

    def say(self, message: str) -> None:
        self.note.configure(text=message)
        self.win.after(8000, lambda: self.note.configure(text="") if self.note.cget("text") == message else None)

    # -- the polling thread and the tick that applies what it found ------------------

    def _poll_loop(self) -> None:
        while not self._quit.is_set():
            try:
                config = load_config(self.locations.config_file)
                status = control.fetch_status(control.reach_host(config.host), config.port, config.token)
            except ConfigError:
                status = None
            self.results.put({"status": status, "gpu": control.gpu_memory()})
            self._quit.wait(POLL_SECONDS)

    def _tick(self) -> None:
        self.drain_lines()
        self.drain_notes()
        latest = None
        while True:
            try:
                latest = self.results.get_nowait()
            except queue.Empty:
                break
        if latest is not None:
            self.apply(latest["status"], latest["gpu"])
        if not self._quit.is_set():
            self._tick_id = self.win.after(150, self._tick)

    def drain_notes(self) -> None:
        while True:
            try:
                self.say(self.notes.get_nowait())
            except queue.Empty:
                return

    def drain_lines(self) -> None:
        added = []
        while True:
            try:
                added.append(self.lines.get_nowait())
            except queue.Empty:
                break
        if not added:
            return
        self.log.configure(state="normal")
        for line in added:
            counted = self.stats.add(line)
            tag = "failed" if counted and _FAILED_LINE.search(line) else ("" if counted else "system")
            self.log.insert("end", line + "\n", tag)
        extra = int(self.log.index("end-1c").split(".")[0]) - MAX_LINES
        if extra > 0:
            self.log.delete("1.0", f"{extra + 1}.0")
        self.log.configure(state="disabled")
        if self.follow.get():
            self.log.see("end")

    def apply(self, status: dict | None, gpu: tuple[int, int] | None) -> None:
        """Show what the server reports. Pure display: safe to call from tests."""
        self.status = status
        self.state, text = control.describe_state(self.server.running, status)
        self.dot.configure(fg=COLOURS[self.state])
        self.state_text.configure(text=text if self.state in ("running", "starting", "stopped") else text.split(".")[0])
        answering = self.state in ("running", "outside")
        live = status if answering else None
        self.info["loaded"].configure(text=control.describe_loaded(live) if live else "-")
        self.info["replies"].configure(text=str(live["replies_in_progress"]) if live else "-")
        seen = self.stats.snapshot()
        self.info["traffic"].configure(text=f"{seen['last_minute']} / {seen['clients']} / {seen['errors']}")
        self.info["uptime"].configure(text=self._uptime(live["uptime_seconds"]) if live else "-")
        self.info["gpu"].configure(text=f"{gpu[0] / 1024:.1f} of {gpu[1] / 1024:.1f} GB used" if gpu else "not available")
        settings = self._settings_quiet()
        self.address.configure(text=self._address_text(settings) if settings and answering else "")
        running = self.server.running
        self.buttons["start"].state(["disabled"] if running else ["!disabled"])
        for key in ("stop", "restart"):
            self.buttons[key].state(["!disabled"] if running else ["disabled"])
        for key in ("open", "link", "token"):
            self.buttons[key].state(["!disabled"] if settings else ["disabled"])

    @staticmethod
    def _uptime(seconds: int) -> str:
        hours, rest = divmod(seconds, 3600)
        return f"{hours}h {rest // 60}m" if hours else f"{rest // 60}m {rest % 60}s"

    def _settings_quiet(self) -> tuple[int, str, str] | None:
        try:
            config = load_config(self.locations.config_file)
        except ConfigError:
            return None
        return config.port, config.token, config.host

    @staticmethod
    def _phone_address(host: str) -> str:
        """The address another device would use: this machine's network address when the server listens everywhere."""
        if host in ("", "0.0.0.0"):
            found = control.lan_addresses()
            return found[0] if found else "127.0.0.1"
        return host

    @staticmethod
    def _is_local(address: str) -> bool:
        return address.startswith("127.") or address == "localhost"

    def _address_text(self, settings: tuple[int, str, str]) -> str:
        address = self._phone_address(settings[2])
        where = "this computer only" if self._is_local(address) else "for your phone"
        return f"http://{address}:{settings[0]}/ ({where})"

    # -- buttons ----------------------------------------------------------------

    def _background(self, work, done_message: str) -> None:
        """Run something slow off the window's thread, then say it is done."""
        def run() -> None:
            work()
            self.notes.put(done_message)
        threading.Thread(target=run, daemon=True).start()

    def start(self) -> None:
        self.say("Starting the server..." if self.server.start() else "The server is already running.")

    def stop(self) -> None:
        self.say("Stopping...")
        self._background(self.server.stop, "Stopped.")

    def restart(self) -> None:
        self.say("Restarting (this loads the code on disk again)...")
        self._background(self.server.restart, "Restarted.")

    def open_page(self) -> None:
        settings = self._settings()
        if settings:
            webbrowser.open(f"http://{control.reach_host(settings[2])}:{settings[0]}/#token={settings[1]}")

    def _copy(self, text: str, message: str) -> None:
        self.win.clipboard_clear()
        self.win.clipboard_append(text)
        self.say(message)

    def copy_link(self) -> None:
        settings = self._settings()
        if settings:
            address = self._phone_address(settings[2])
            note = ("Login link copied. The server only listens on this computer, so the link works only here."
                    if self._is_local(address) else
                    "Login link copied. It contains the token: send it only to your own devices.")
            self._copy(f"http://{address}:{settings[0]}/#token={settings[1]}", note)

    def copy_token(self) -> None:
        settings = self._settings()
        if settings:
            self._copy(settings[1], "Token copied.")

    def free_gpu(self) -> None:
        settings = self._settings()
        if not settings:
            return
        self.say("Freeing GPU memory...")

        def work() -> None:
            if self.state in ("running", "outside"):
                result = control.free_gpu(control.reach_host(settings[2]), settings[0], settings[1])
                text = "no answer from the server" if result is None else (
                    result.get("error") or "freed " + ", ".join(
                        name for held in result.get("unloaded", {}).values() if isinstance(held, list) for name in held)
                    or "nothing was loaded")
            else:
                text = (control.run_cli(self.root, "unload").splitlines() or ["done"])[0]
            self.notes.put(f"GPU: {text}")
        threading.Thread(target=work, daemon=True).start()

    def clear_log(self) -> None:
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def shutdown(self) -> None:
        """Stop everything this panel started: its timer, the server and its polling thread. Safe to call twice."""
        self._quit.set()
        try:
            self.win.after_cancel(self._tick_id)
        except tk.TclError:
            pass
        self.server.stop()
        self._poll.join(timeout=POLL_SECONDS + 4)

    def close(self) -> None:
        busy = bool(self.status and self.status.get("replies_in_progress"))
        if self.server.running and busy and not messagebox.askokcancel(
                "_HomeAGENT", "A reply is still being written. Stop the server and close anyway?"):
            return
        self.shutdown()
        self.win.destroy()


def run(autostart: bool = True) -> int:
    win = tk.Tk()
    Panel(win, repo_locations().root, autostart)
    win.mainloop()
    return 0
