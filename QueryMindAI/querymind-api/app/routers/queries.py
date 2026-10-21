from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.sse import EventSourceResponse, ServerSentEvent
from querymind.service import QueryMindService

from app.dependencies import get_service
from app.schemas import AskRequest, AskResponse, RunRequest, RunResponse
from app.streaming import stream_operation

router = APIRouter(tags=["queries"])

Service = Annotated[QueryMindService, Depends(get_service)]


def checked_run_request(body: RunRequest, service: Service) -> RunRequest:
    """Validate against server limits before any response (or stream) starts."""
    limit = service.settings.max_rows
    if body.max_rows is not None and body.max_rows > limit:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"max_rows cannot exceed {limit}")
    return body


CheckedRunRequest = Annotated[RunRequest, Depends(checked_run_request)]

STREAM_DESCRIPTION = """

Streams Server-Sent Events while the work runs:
`progress` events (`{id, status, message, detail}`; each step is reported `running`, then `done` or `failed`),
then one `result` event with the same body as the non-streaming endpoint,
or one `error` event (`{status, detail}`). Closing the connection cancels the work."""


@router.post("/ask", response_model=AskResponse)
def ask(body: AskRequest, service: Service) -> AskResponse:
    """Retrieve context and generate SQL for the question, without running it."""
    return AskResponse.from_result(service.ask(body.question, database=body.database))


@router.post(
    "/ask/stream",
    response_class=EventSourceResponse,
    summary="Ask (streaming)",
    description="Same as `POST /ask`, with live progress." + STREAM_DESCRIPTION,
)
async def ask_stream(body: AskRequest, service: Service) -> AsyncIterator[ServerSentEvent]:
    def work(on_progress):
        return AskResponse.from_result(service.ask(body.question, database=body.database, on_progress=on_progress))

    async for event in stream_operation(work):
        yield event


@router.post("/run", response_model=RunResponse)
def run(body: CheckedRunRequest, service: Service) -> RunResponse:
    """Generate SQL, run it read-only on the databases, and answer from the results.

    Every question is classified first (`intent`). DELETE, INSERT and DDL requests are refused
    (`status: blocked`) before any SQL is written; UPDATE requests are drafted and returned but never
    executed (`status: generated`). All statuses return 200.
    """
    result = service.run(body.question, database=body.database, max_repairs=body.max_repairs,
                         max_rows=body.max_rows, use_cache=body.use_cache)
    return RunResponse.from_result(result)


@router.post(
    "/run/stream",
    response_class=EventSourceResponse,
    summary="Run (streaming)",
    description="Same as `POST /run`, with live progress." + STREAM_DESCRIPTION,
)
async def run_stream(body: CheckedRunRequest, service: Service) -> AsyncIterator[ServerSentEvent]:
    def work(on_progress):
        result = service.run(body.question, database=body.database, max_repairs=body.max_repairs,
                             max_rows=body.max_rows, on_progress=on_progress, use_cache=body.use_cache)
        return RunResponse.from_result(result)

    async for event in stream_operation(work):
        yield event

