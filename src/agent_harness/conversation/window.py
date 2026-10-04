"""Which turns fit in the model's context: token estimates that learn from what the backend reports."""

from __future__ import annotations

import math
from dataclasses import dataclass

DEFAULT_RATIO = 3.5  # characters per token before a model has been measured: a cautious guess for English
PER_MESSAGE = 6      # chat-template tokens wrapped around each message
BASE = 8             # tokens for the request as a whole
MARGIN = 0.10        # share of the context kept free for estimate error
MIN_BUDGET = 256


class ContextTooLarge(Exception):
    """The newest message cannot fit in the budget even with nothing before it."""

    def __init__(self, needed: int, budget: int, what: str = "message"):
        subject = "The system prompt alone needs" if what == "system prompt" else "This message needs"
        super().__init__(f"{subject} about {needed} tokens but at most {budget} fit in the model's context. "
                         f"Shorten it, or raise num_ctx in the config.")
        self.needed, self.budget = needed, budget


class TokenEstimator:
    """Estimates tokens from characters, per model. Each reply's reported prompt size corrects the ratio."""

    def __init__(self):
        self._ratio: dict[str, float] = {}

    def ratio(self, model: str) -> float:
        return self._ratio.get(model, DEFAULT_RATIO)

    def text(self, model: str, chars: int) -> int:
        return math.ceil(chars / self.ratio(model))

    def message(self, model: str, message: dict) -> int:
        return PER_MESSAGE + self.text(model, len(message["content"]))

    def messages(self, model: str, messages: list[dict]) -> int:
        return BASE + sum(self.message(model, m) for m in messages)

    def learn(self, model: str, chars: int, message_count: int, prompt_tokens: int | None) -> None:
        """Move this model's ratio toward what the backend reported for a prompt of `chars` characters."""
        if not isinstance(prompt_tokens, int) or chars < 8:
            return
        content_tokens = prompt_tokens - BASE - PER_MESSAGE * message_count
        if content_tokens < 8:  # too small to say anything useful
            return
        sample = min(6.0, max(1.5, chars / content_tokens))
        old = self.ratio(model)
        # More tokens per character is the safe direction, so it is believed at once. Fewer is believed
        # slowly: a backend that reports a short count (caching, truncation) must not make estimates too low.
        self._ratio[model] = sample if sample < old else 0.7 * old + 0.3 * sample


def largest_reply(num_ctx: int) -> int:
    """The longest reply that still leaves the prompt its minimum budget."""
    return int(num_ctx * (1 - MARGIN)) - MIN_BUDGET


def budget_tokens(num_ctx: int, reply_tokens: int) -> int:
    """Tokens available for the prompt: the context, less a safety margin, less room for the reply."""
    return max(MIN_BUDGET, int(num_ctx * (1 - MARGIN)) - reply_tokens)


@dataclass(frozen=True)
class Window:
    messages: list[dict]  # what is sent, the system prompt first
    start: int            # index, among the conversation's turns, of the first turn sent
    sent: int             # history messages sent
    dropped: int          # older history messages left out (they stay in the record)
    estimated_tokens: int
    budget: int
    chars: int            # characters sent, system prompt included
    message_count: int    # messages sent, system prompt included

    def record(self) -> dict:
        """What is stored with the reply and shown to the user."""
        return {"start": self.start, "sent": self.sent, "dropped": self.dropped,
                "estimated_tokens": self.estimated_tokens, "budget": self.budget,
                "chars": self.chars, "messages": self.message_count}


def choose_window(history: list[tuple[int, dict]], system_prompt: str, model: str,
                  estimator: TokenEstimator, budget: int) -> Window:
    """Send the newest turns that fit. `history` is (turn index, message), oldest first, newest last.

    The newest message always goes; older ones are added back to front until the budget is spent,
    so what is sent is one unbroken run ending at the newest message. Raises ContextTooLarge if even
    the newest message alone does not fit."""
    system = [{"role": "system", "content": system_prompt}] if system_prompt else []
    used = estimator.messages(model, system)
    if used > budget:
        raise ContextTooLarge(used, budget, "system prompt")
    kept: list[tuple[int, dict]] = []
    if history:
        newest = history[-1]
        used += estimator.message(model, newest[1])
        if used > budget:
            raise ContextTooLarge(used, budget)
        kept.append(newest)
        for index, message in reversed(history[:-1]):
            cost = estimator.message(model, message)
            if used + cost > budget:
                break
            used += cost
            kept.append((index, message))
        kept.reverse()
    sent = system + [m for _, m in kept]
    return Window(sent, kept[0][0] if kept else 0, len(kept), len(history) - len(kept), used, budget,
                  sum(len(m["content"]) for m in sent), len(sent))
