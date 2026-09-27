"""Exercise both clients through HTTP transports against public monitor wire fixtures."""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from transcriptfetch import AsyncTranscriptFetch, NotFoundError, TranscriptFetch

FIXTURES = json.loads(Path(__file__).with_name("monitor-fixtures.json").read_text())
BASE = "https://example.test"


async def resolve(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


@pytest.fixture(params=[False, True], ids=["sync", "async"])
def asynchronous(request: Any) -> bool:
    return bool(request.param)


def setup(asynchronous: bool, handler: Any) -> tuple[Any, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request, len(requests))

    transport = httpx.MockTransport(handle)
    http = (httpx.AsyncClient if asynchronous else httpx.Client)(base_url=BASE, transport=transport)
    client = (AsyncTranscriptFetch if asynchronous else TranscriptFetch)(
        api_key="test-only", base_url=BASE, max_retries=1, http_client=http
    )
    return client, requests


async def close(client: Any) -> None:
    # Caller owns the injected transport.
    await resolve(
        client._http.aclose() if isinstance(client, AsyncTranscriptFetch) else client._http.close()
    )


async def test_create(asynchronous: bool) -> None:
    client, requests = setup(
        asynchronous, lambda *_: httpx.Response(201, json=FIXTURES["createMonitor"])
    )
    try:
        monitor = await resolve(
            client.monitors.create(
                "@fixture",
                platform="youtube",
                tab="shorts",
                webhook_url="https://example.test/hook",
                interval_minutes=360,
                transcripts=False,
                name="Mine",
                idempotency_key="create-key",
            )
        )
        assert json.loads(requests[0].content) == {
            "target": "@fixture",
            "type": "channel",
            "platform": "youtube",
            "tab": "shorts",
            "webhook_url": "https://example.test/hook",
            "interval_minutes": 360,
            "transcripts": False,
            "name": "Mine",
        }
        assert requests[0].url.path == "/api/v2/monitors"
        assert requests[0].headers["authorization"] == "Bearer test-only"
        assert requests[0].headers["idempotency-key"] == "create-key"
        assert monitor.webhook_secret == "whsec_…"
        assert monitor.baseline_count == 30
        assert monitor.usage.credits_spent == 0
        assert "whsec_" not in repr(monitor)
    finally:
        await close(client)


async def test_minimal_create_retry(asynchronous: bool) -> None:
    client, requests = setup(
        asynchronous,
        lambda _, n: (
            httpx.Response(
                503,
                json={"error": {"code": "internal_error", "message": "retry"}},
                headers={"Retry-After": "0"},
            )
            if n == 1
            else httpx.Response(201, json=FIXTURES["createMonitor"])
        ),
    )
    try:
        await resolve(client.monitors.create("@fixture"))
        assert len(requests) == 2
        assert json.loads(requests[0].content) == {"target": "@fixture", "type": "channel"}
        assert requests[0].headers["idempotency-key"] == requests[1].headers["idempotency-key"]
    finally:
        await close(client)


async def test_read_update_delete(asynchronous: bool) -> None:
    def handler(request: httpx.Request, _: int) -> httpx.Response:
        fixture = (
            "deleteMonitor"
            if request.method == "DELETE"
            else "updateMonitor"
            if request.method == "PATCH"
            else "listMonitors"
            if request.url.path.endswith("/monitors")
            else "getMonitor"
        )
        return httpx.Response(200, json=FIXTURES[fixture])

    client, requests = setup(asynchronous, handler)
    try:
        monitors = await resolve(client.monitors.list(since="mev_a+b&c"))
        assert monitors.has_new is True
        assert monitors.limits.min_interval_minutes == 15
        assert requests[-1].url.params["since"] == "mev_a+b&c"
        assert "idempotency-key" not in requests[-1].headers
        monitor = await resolve(client.monitors.get("mon/a?x", since=monitors.last_event_id))
        assert b"mon%2Fa%3Fx" in requests[-1].url.raw_path
        assert monitor.webhook_secret is None
        assert requests[-1].url.params["since"] == monitors.last_event_id
        paused = await resolve(
            client.monitors.update(
                "mon_1", webhook_url=None, name=None, transcripts=False, status="paused"
            )
        )
        assert requests[-1].method == "PATCH"
        assert json.loads(requests[-1].content) == {
            "webhook_url": None,
            "name": None,
            "transcripts": False,
            "status": "paused",
        }
        assert paused.status == "paused"
        assert paused.next_check_at is None
        deleted = await resolve(client.monitors.delete("mon_1"))
        assert requests[-1].method == "DELETE"
        assert deleted.kind == "monitor_deleted"
    finally:
        await close(client)


async def test_check(asynchronous: bool) -> None:
    failed = {
        **FIXTURES["checkMonitor"],
        "data": {
            **FIXTURES["checkMonitor"]["data"],
            "new_videos": 0,
            "event": None,
            "error": {"code": "not_found", "message": "Channel gone", "number": 4004},
        },
    }
    client, requests = setup(
        asynchronous,
        lambda _, n: httpx.Response(200, json=FIXTURES["checkMonitor"] if n == 1 else failed),
    )
    try:
        result = await resolve(client.monitors.check("mon_1", idempotency_key="check-key"))
        assert requests[0].url.path == "/api/v2/monitors/mon_1/check"
        assert requests[0].headers["idempotency-key"] == "check-key"
        assert result.new_videos == 1
        assert result.usage.credits_spent == 2
        assert result.event.data.videos[0].video_id == "dQw4w9WgXcQ"
        assert result.event.data.transcripts[0].transcript.segments[0].text
        assert result.event.delivery.status == "delivered"
        result = await resolve(client.monitors.check("mon_1"))
        assert result.error.code == "not_found"
        assert result.event is None
    finally:
        await close(client)


async def test_event_pages_and_followup(asynchronous: bool) -> None:
    page = json.loads(json.dumps(FIXTURES["listMonitorEvents"]))
    page["data"]["next_cursor"] = "a+/=&"
    followup = {
        **page["data"]["events"][0],
        "id": "mev_followup",
        "type": "monitor.transcript",
        "data": {
            "video_id": "v2",
            "url": "https://example.test/v2",
            "outcome": "error",
            "error": {"code": "no_captions", "message": "none", "number": 3001},
            "videos_event_id": "mev_parent",
        },
    }
    end = {**page, "data": {**page["data"], "events": [followup], "next_cursor": None}}
    client, requests = setup(
        asynchronous, lambda _, n: httpx.Response(200, json=page if n == 1 else end)
    )
    try:
        iterator = client.monitors.iter_events("mon_1", limit=1, since="mev_before")
        events = [event async for event in iterator] if asynchronous else list(iterator)
        assert len(events) == 2
        assert len(requests) == 2
        assert requests[1].url.params["cursor"] == "a+/=&"
        assert all(r.url.params["since"] == "mev_before" for r in requests)
        assert all(r.url.params["limit"] == "1" for r in requests)
        assert events[1].data.videos_event_id == "mev_parent"
        assert events[1].data.error.code == "no_captions"
    finally:
        await close(client)


async def test_http_error_mapping(asynchronous: bool) -> None:
    client, _ = setup(
        asynchronous,
        lambda *_: httpx.Response(
            404,
            json={
                "ok": False,
                "error": {"code": "not_found", "message": "Missing", "number": 4004},
                "request_id": "req_error",
            },
        ),
    )
    try:
        with pytest.raises(NotFoundError):
            await resolve(client.monitors.get("missing"))
    finally:
        await close(client)


async def test_video_builder_options(asynchronous: bool) -> None:
    client, requests = setup(
        asynchronous,
        lambda *_: httpx.Response(
            200, json={"ok": True, "data": {"text": "hello"}, "usage": {"credits_spent": 1}}
        ),
    )
    try:
        await resolve(
            client.transcripts.video(
                "video", mode="captions", timestamps=False, callback_url="https://example.test/hook"
            )
        )
        assert json.loads(requests[0].content) == {
            "video": "video",
            "mode": "captions",
            "timestamps": False,
            "callback_url": "https://example.test/hook",
        }
    finally:
        await close(client)


async def test_processing_and_successful_followup(asynchronous: bool) -> None:
    page = json.loads(json.dumps(FIXTURES["listMonitorEvents"]))
    original = page["data"]["events"][0]
    entry = original["data"]["transcripts"][0]
    original["data"]["transcripts"].append(
        {
            "video_id": "queued",
            "url": "https://example.test/q",
            "outcome": "processing",
            "job_id": "asr_fixture",
        }
    )
    page["data"]["events"].append(
        {
            **original,
            "id": "mev_done",
            "type": "monitor.transcript",
            "data": {**entry, "videos_event_id": original["id"]},
        }
    )
    client, _ = setup(asynchronous, lambda *_: httpx.Response(200, json=page))
    try:
        events = (await resolve(client.monitors.events("mon_1"))).events
        assert events[0].data.transcripts[1].job_id == "asr_fixture"
        assert events[0].data.transcripts[1].outcome == "processing"
        assert events[1].data.transcript.video_id == entry["video_id"]
        assert events[1].data.transcript.channel == "Example Channel"
        assert events[1].data.videos_event_id == original["id"]
    finally:
        await close(client)
