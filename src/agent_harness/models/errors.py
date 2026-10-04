"""Failures from a model backend, with a reason code the rest of the system can act on."""

from __future__ import annotations

# Seen by the transport: unreachable, timeout_connect, timeout_listing, timeout_first_byte,
#   timeout_idle, deadline, connection_reset, http_error.
# Seen only by an adapter, which knows the protocol: protocol_error, incomplete, context_exceeded.
REASONS = ("unreachable", "timeout_connect", "timeout_listing", "timeout_first_byte", "timeout_idle",
           "deadline", "connection_reset", "http_error", "protocol_error", "incomplete",
           "context_exceeded")


class BackendError(RuntimeError):
    """A backend call failed. `message` is fit to show to the person using it; `partial_text` is what streamed first."""

    def __init__(self, reason: str, message: str, *, status: int | None = None,
                 detail: str = "", partial_text: str = ""):
        if reason not in REASONS:
            raise ValueError(f"Unknown backend failure reason: {reason!r}")
        super().__init__(message)
        self.reason = reason
        self.message = message
        self.status = status
        self.detail = detail
        self.partial_text = partial_text


class UnknownModelChoice(ValueError):
    """The chosen `backend_id:model` does not name a configured backend."""
