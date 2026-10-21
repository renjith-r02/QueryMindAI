import json
import threading
import time

import pytest
from pydantic import BaseModel
from querymind.exceptions import MissingApiKeyError
from querymind.progress import Progress, ProgressEvent

from app.streaming import stream_operation


def read_events(response) -> list[tuple[str, dict]]:
    """Parse a text/event-stream body into (event, data) pairs, skipping keep-alive comments."""
    events = []
    for block in response.text.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if not line.startswith(":"))
        if fields:
            events.append((fields["event"], json.loads(fields["data"])))
    return events


def test_run_stream_sends_progress_then_result(client):
    with client.stream("POST", "/run/stream", json={"question": "list n", "max_rows": 2}) as response:
        response.read()
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events = read_events(response)
    kinds = [kind for kind, _ in events]
    assert kinds[-1] == "result" and set(kinds[:-1]) == {"progress"}

    steps = [(data["id"], data["status"]) for kind, data in events if kind == "progress"]
    assert steps[:6] == [
        ("cache", "running"),
        ("cache", "done"),
        ("classify", "running"),
        ("classify", "done"),
        ("retrieve", "running"),
        ("retrieve", "done"),
    ]
    assert ("execute-1-1", "done") in steps and steps[-1] == ("answer", "done")

    result = events[-1][1]
    assert result["status"] == "answered"
    assert result["result"]["rows"] == [[1], [2]]


def test_ask_stream(client):
    with client.stream("POST", "/ask/stream", json={"question": "list n"}) as response:
        response.read()
    events = read_events(response)
    assert [data["id"] for kind, data in events if kind == "progress"] == [
        "classify",
        "classify",
        "retrieve",
        "retrieve",
        "generate-1",
        "generate-1",
    ]
    assert events[-1][0] == "result"
    assert events[-1][1]["answer"]["queries"][0]["sql"] == "SELECT n FROM t ORDER BY n"


def test_stream_reports_service_errors_as_events(client, service, monkeypatch):
    def fail(*args, on_progress=None, **kwargs):
        Progress(on_progress).running("retrieve", "Searching")
        raise MissingApiKeyError("no key")

    monkeypatch.setattr(service, "run", fail)
    with client.stream("POST", "/run/stream", json={"question": "q"}) as response:
        response.read()
    assert response.status_code == 200  # the stream had already started
    events = read_events(response)
    assert events[0][0] == "progress"
    assert events[-1] == (
        "error",
        {"status": 503, "detail": "The model provider's API key is not configured on the server."},
    )


def test_stream_validates_before_streaming(client):
    response = client.post("/run/stream", json={"question": "q", "max_rows": 101})
    assert response.status_code == 422
    response = client.post("/run/stream", json={"question": "q", "llm_model": "x"})
    assert response.status_code == 422


class Done(BaseModel):
    steps: int


@pytest.mark.anyio
async def test_disconnect_cancels_the_work():
    stopped = threading.Event()
    reached = []

    def work(on_progress):
        try:
            for step in range(100):
                reached.append(step)
                on_progress(ProgressEvent(f"step-{step}", "running", f"Step {step}"))
                time.sleep(0.01)
            return Done(steps=100)
        finally:
            stopped.set()

    events = stream_operation(work)
    first = await anext(events)
    assert first.event == "progress"
    await events.aclose()  # what the server does when the client goes away

    assert stopped.wait(timeout=2), "the worker kept running after the client left"
    assert len(reached) < 100



def test_run_stream_refuses_delete(client):
    with client.stream("POST", "/run/stream", json={"question": "delete all orders"}) as response:
        response.read()
    events = read_events(response)
    assert [(data["id"], data["status"]) for kind, data in events if kind == "progress"] == [
        ("classify", "running"),
        ("classify", "failed"),
    ]
    result = events[-1][1]
    assert events[-1][0] == "result" and result["status"] == "blocked"
    assert result["intent"]["query_type"] == "UNSUPPORTED"
