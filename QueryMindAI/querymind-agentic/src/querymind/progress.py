"""Progress events for long-running operations (streamed to clients as they happen).

Each step has a stable id; it is reported "running" when it starts and "done" or
"failed" when it ends, so a client can update the same line in place:

    retrieve -> schema -> generate-1 -> execute-1-1 ... -> merge-1 -> generate-2 ... -> answer
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Status = Literal["running", "done", "failed"]


@dataclass
class ProgressEvent:
    id: str
    status: Status
    message: str
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


ProgressCallback = Callable[[ProgressEvent], None]


class Progress:
    """Sends events to an optional callback. The callback may raise to cancel the work."""

    def __init__(self, callback: ProgressCallback | None = None):
        self.callback = callback

    def running(self, step: str, message: str, **detail: Any) -> None:
        self._emit(step, "running", message, detail)

    def done(self, step: str, message: str, **detail: Any) -> None:
        self._emit(step, "done", message, detail)

    def failed(self, step: str, message: str, **detail: Any) -> None:
        self._emit(step, "failed", message, detail)

    def _emit(self, step: str, status: Status, message: str, detail: dict[str, Any]) -> None:
        if self.callback is not None:
            self.callback(ProgressEvent(step, status, message, detail))


def plural(count: int, word: str, plural_word: str | None = None) -> str:
    return f"{count} {word if count == 1 else plural_word or word + 's'}"
