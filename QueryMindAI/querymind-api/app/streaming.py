"""Run a blocking QueryMind operation in a worker thread and stream its progress as SSE.

Events sent, in order:

    event: progress   data: {"id", "status", "message", "detail"}   (zero or more)
    event: result     data: <the same body the non-streaming endpoint returns>
 or event: error      data: {"status": <http status>, "detail": "<message>"}

If the client disconnects, the operation is cancelled at its next progress step.
"""

import asyncio
import threading
from collections.abc import AsyncIterator, Callable

from fastapi.sse import ServerSentEvent
from pydantic import BaseModel
from querymind.progress import ProgressCallback, ProgressEvent

from app.errors import describe_error


class StreamCancelled(Exception):
    """Raised inside the worker when the client has gone away."""


_DONE = object()


async def stream_operation(
    work: Callable[[ProgressCallback], BaseModel],
) -> AsyncIterator[ServerSentEvent]:
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    cancelled = threading.Event()

    def send(item: object) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, item)

    def on_progress(event: ProgressEvent) -> None:
        if cancelled.is_set():
            raise StreamCancelled
        send(ServerSentEvent(event="progress", data=event.to_dict()))

    def worker() -> None:
        try:
            send(ServerSentEvent(event="result", data=work(on_progress).model_dump(mode="json")))
        except StreamCancelled:
            pass
        except Exception as error:  # noqa: BLE001 - every failure is reported to the client as an event
            status_code, detail = describe_error(error)
            send(ServerSentEvent(event="error", data={"status": status_code, "detail": detail}))
        finally:
            send(_DONE)

    # The worker catches every error itself, so the future is not awaited after a disconnect.
    loop.run_in_executor(None, worker)
    try:
        while (item := await queue.get()) is not _DONE:
            yield item
    finally:
        # Reached on completion and when the client disconnects (the generator is closed);
        # the worker then stops at its next progress step.
        cancelled.set()
