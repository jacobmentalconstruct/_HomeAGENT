"""One reply = one Generation on its own thread. Clients subscribe; the reply never depends on them."""

from __future__ import annotations

import queue
import threading
import time
import uuid
from collections import OrderedDict

from ..models.errors import BackendError
from ..models.registry import ModelRegistry
from . import overflow
from .manager import ConversationManager
from .window import ContextTooLarge, TokenEstimator, budget_tokens, choose_window

KEEP_FINISHED = 50
SUBSCRIBER_BUFFER = 2000


class Turnstile:
    """First come, first served, one at a time. Position 0 means it is your turn."""

    def __init__(self):
        self._cond = threading.Condition()
        self._next = 0
        self._serving = 0

    def take(self) -> int:
        with self._cond:
            ticket, self._next = self._next, self._next + 1
            return ticket

    def position(self, ticket: int) -> int:
        with self._cond:
            return ticket - self._serving

    def wait_turn(self, ticket: int, on_change) -> None:
        last = None
        with self._cond:
            while ticket != self._serving:
                ahead = ticket - self._serving
                if ahead != last:
                    last = ahead
                    try:
                        on_change(ahead)
                    except Exception:  # a failing observer must never stall the queue
                        pass
                self._cond.wait()

    def done(self) -> None:
        with self._cond:
            self._serving += 1
            self._cond.notify_all()


class Generation:
    """Live state of one reply: text so far, state, and the clients watching it."""

    def __init__(self, generation_id: str, conversation_id: str, model: str, prompt: str = ""):
        self.id, self.conversation_id, self.model = generation_id, conversation_id, model
        self.prompt = prompt
        self.state = "queued"  # queued, running, done, failed
        self.position = 0
        self.text = ""
        self.error: dict | None = None
        self.summary: dict | None = None
        self.window: dict | None = None  # what this reply was sent, once it starts
        self.finished = threading.Event()  # set once the reply has a final outcome
        self._lock = threading.Lock()
        self._subscribers: list[queue.Queue] = []

    def snapshot(self) -> dict:
        with self._lock:
            return self._snapshot()

    def _snapshot(self) -> dict:
        return {"type": "snapshot", "generation_id": self.id, "state": self.state, "position": self.position,
                "text": self.text, "error": self.error, "summary": self.summary, "window": self.window}

    def subscribe(self) -> tuple[dict, queue.Queue]:
        """A snapshot and a queue of everything after it, taken atomically so nothing is missed or doubled."""
        with self._lock:
            q: queue.Queue = queue.Queue(SUBSCRIBER_BUFFER)
            if self.state in ("queued", "running"):
                self._subscribers.append(q)
            return self._snapshot(), q

    def publish(self, message: dict, *, final: bool = False) -> None:
        with self._lock:
            kind = message["type"]
            if kind == "delta":
                self.text += message["text"]
            elif kind == "reset":
                self.text = ""
            elif kind == "position":
                self.position = message["position"]
            elif kind == "running":
                self.state, self.position, self.window = "running", 0, message.get("window")
            elif kind == "done":
                self.state, self.summary = "done", message["summary"]
            elif kind == "failed":
                self.state, self.error = "failed", message["error"]
            for q in list(self._subscribers):
                try:
                    q.put_nowait(message)
                    if final:
                        q.put_nowait(None)  # end of stream
                except queue.Full:  # a client that cannot keep up is dropped; it can reattach
                    self._subscribers.remove(q)
            if final:
                self._subscribers.clear()
                self.finished.set()


class GenerationRunner:
    """Starts replies and keeps the live registry. Orders model use per backend, first come first served."""

    def __init__(self, conversations: ConversationManager, models: ModelRegistry, *,
                 system_prompt: str = "", num_ctx: int = 8192, reply_tokens: int = 2048,
                 options: dict | None = None, memory=None):
        self.conversations, self.models = conversations, models
        self.system_prompt, self.options = system_prompt, options
        self.memory = memory
        self.num_ctx = num_ctx
        self.budget = budget_tokens(num_ctx, reply_tokens)
        self.estimator = TokenEstimator()
        for sample in conversations.samples():  # remember what past replies measured
            self.estimator.learn(*sample)
        self._turnstiles = {backend_id: Turnstile() for backend_id in models.backends}  # fixed, so no race
        self._gens: OrderedDict[str, Generation] = OrderedDict()
        self._lock = threading.Lock()

    def active_count(self) -> int:
        """How many replies are waiting or running."""
        with self._lock:
            return sum(1 for g in self._gens.values() if g.state in ("queued", "running"))

    def active(self) -> bool:
        """True while any reply is waiting or running."""
        return self.active_count() > 0

    def get(self, generation_id: str) -> Generation | None:
        with self._lock:
            return self._gens.get(generation_id)

    def send(self, conversation_id: str, text: str, choice: str, client: str = "") -> Generation:
        """Record the user turn and start the reply. Raises KeyError, Busy, UnknownModelChoice."""
        backend, model = self.models.resolve(choice)
        generation_id = uuid.uuid4().hex
        self.conversations.begin_turn(conversation_id, generation_id, text, choice, client)
        gen = Generation(generation_id, conversation_id, choice, text)
        with self._lock:
            self._gens[generation_id] = gen
            while len(self._gens) > KEEP_FINISHED:
                oldest = next(iter(self._gens))
                if self._gens[oldest].state in ("queued", "running"):
                    break
                del self._gens[oldest]
        turnstile = self._turnstiles[backend.config.id]
        ticket = turnstile.take()
        gen.publish({"type": "position", "position": turnstile.position(ticket)})
        threading.Thread(target=self._run, args=(gen, backend, model, turnstile, ticket),
                         name=f"gen-{generation_id[:6]}", daemon=True).start()
        return gen

    def _run(self, gen: Generation, backend, model: str, turnstile: Turnstile, ticket: int) -> None:
        stream = None
        try:
            turnstile.wait_turn(ticket, lambda ahead: gen.publish({"type": "position", "position": ahead}))
            deadline = time.monotonic() + backend.transport.timeouts.total
            try:
                history = self.conversations.history_indexed(gen.conversation_id)
                system = [{"role": "system", "content": self.system_prompt}] if self.system_prompt else []
                system_tokens = self.estimator.messages(model, system)
                if system_tokens > self.budget:
                    error = ContextTooLarge(system_tokens, self.budget, "system prompt")
                    raise BackendError("context_exceeded", str(error))
                query = gen.prompt
                if history and self.estimator.messages(model, system + [history[-1][1]]) > self.budget:
                    query = overflow.bounded_question(gen.prompt, max(64, int(self.budget * self.estimator.ratio(model))))
                retrieved = (self.memory.retrieve(query, gen.conversation_id,
                                                  self.conversations.event_history(gen.conversation_id))
                             if self.memory is not None else [])
                window = choose_window(history, self.system_prompt, gen.model,
                                       self.estimator, self.budget, retrieved)
                derived = None
            except ContextTooLarge as exc:
                derived, history = self._derive(gen, backend, model, history, retrieved, deadline,
                                                overflow_message=str(exc))
                window = choose_window(history, self.system_prompt, gen.model,
                                       self.estimator, self.budget, retrieved)
            window_record = window.record()
            if self.memory is not None:
                window_record["memory"] = self.memory.status()
            if derived is not None:
                window_record["derived"] = derived
            gen.publish({"type": "running", "window": window_record})
            try:
                stream = backend.chat(model, window.messages, self.options, deadline=deadline)
                for chunk in stream:
                    gen.publish({"type": "delta", "text": chunk})
            except BackendError as exc:
                if exc.reason != "context_exceeded" or derived is not None or backend.config.kind != "ollama":
                    raise
                gen.publish({"type": "reset"})
                stream = None
                history = self.conversations.history_indexed(gen.conversation_id)
                derived, history = self._derive(gen, backend, model, history, retrieved, deadline,
                                                overflow_message=exc.message)
                window = choose_window(history, self.system_prompt, gen.model,
                                       self.estimator, self.budget, retrieved)
                window_record = window.record()
                if self.memory is not None:
                    window_record["memory"] = self.memory.status()
                window_record["derived"] = derived
                gen.publish({"type": "running", "window": window_record})
                stream = backend.chat(model, window.messages, self.options, deadline=deadline)
                for chunk in stream:
                    gen.publish({"type": "delta", "text": chunk})
            summary = stream.summary
            self.estimator.learn(gen.model, window.chars, window.message_count, summary.prompt_tokens)
            self.conversations.finish_turn(gen.conversation_id, gen.id, stream.text, gen.model, summary,
                                           window_record)
            gen.publish({"type": "done", "summary": {"stop_reason": summary.stop_reason,
                                                    "prompt_tokens": summary.prompt_tokens,
                                                    "reply_tokens": summary.reply_tokens}}, final=True)
        except BackendError as exc:
            self._fail(gen, exc.reason, exc.message, exc.partial_text or (stream.text if stream else ""))
        except Exception as exc:  # a bug must still end the reply visibly
            self._fail(gen, "internal_error", f"{type(exc).__name__}: {exc}", stream.text if stream else gen.text)
        finally:
            turnstile.done()
            if gen.state in ("queued", "running"):  # last resort: never leave a reply unresolved
                self._fail(gen, "internal_error", "The reply ended without a result.", gen.text)

    def _derive(self, gen: Generation, backend, model, history: list[tuple[int, dict]],
                retrieved: list[dict], deadline: float, overflow_message: str = "") -> tuple[dict, list[tuple[int, dict]]]:
        event = next((item for item in reversed(self.conversations.event_history(gen.conversation_id))
                      if item.kind == "turn.user" and item.payload.get("generation_id") == gen.id), None)
        if event is None:
            raise BackendError("context_exceeded", "The source event for this message is unavailable.")
        return overflow.derive_context(
            gen.prompt, history, event.seq, model, backend, self.estimator, self.budget,
            self.num_ctx, self.system_prompt, retrieved, self.options, deadline,
            lambda phase, completed, total: gen.publish({"type": "progress", "phase": phase,
                                                          "completed": completed, "total": total}),
            overflow_message=overflow_message)

    def _fail(self, gen: Generation, reason: str, message: str, partial: str) -> None:
        self.conversations.fail_turn(gen.conversation_id, gen.id, gen.model, reason, message, partial)
        gen.publish({"type": "failed", "error": {"reason": reason, "message": message,
                                                 "partial_text": partial}}, final=True)
