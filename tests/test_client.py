from __future__ import annotations

import json

import httpx
import pytest
import respx

from tests.data import (
    BASE,
    BATCH_ENV,
    HEALTH,
    JOB_ACCEPTED_ENV,
    JOB_DONE_ENV,
    JOB_PROCESSING_ENV,
    ME_ENV,
    VIDEO_ENV,
    video_list,
)
from transcriptfetch import TranscriptFetch


def _client() -> TranscriptFetch:
    return TranscriptFetch(api_key="tf_test", base_url=BASE, max_retries=0)


@respx.mock
def test_video_parses_and_sends_headers() -> None:
    route = respx.post(f"{BASE}/api/v2/transcripts/video").mock(
        return_value=httpx.Response(200, json=VIDEO_ENV)
    )
    with _client() as tf:
        t = tf.transcripts.video("dQw4w9WgXcQ")

    assert t.video_id == "abc"
    # The one metadata block every transcript carries (API contract of 2026-09-15).
    assert t.url == "https://www.youtube.com/watch?v=abc"
    assert t.platform == "youtube"
    assert t.channel == "Example Channel"
    assert t.duration == 212
    assert t.language == "en"
    assert t.thumbnail_url == "https://i.ytimg.com/vi/abc/mqdefault.jpg"
    assert t.source == "captions"
    assert t.text == "hello world"
    assert t.segments[0].text == "hi"
    assert t.usage is not None and t.usage.balance == 99

    req = route.calls.last.request
    assert req.headers["authorization"] == "Bearer tf_test"
    assert req.headers.get("idempotency-key")  # auto-generated
    assert json.loads(req.content)["video"] == "dQw4w9WgXcQ"


@respx.mock
def test_channel_auto_pagination() -> None:
    respx.post(f"{BASE}/api/v2/transcripts/channel").mock(
        side_effect=[
            httpx.Response(200, json=video_list([{"videoId": "a", "title": "A"}], "cur1")),
            httpx.Response(200, json=video_list([{"videoId": "b", "title": "B"}], None)),
        ]
    )
    with _client() as tf:
        ids = [v.video_id for v in tf.transcripts.iter_channel("@x", limit=1)]
    assert ids == ["a", "b"]


@respx.mock
def test_video_list_camelcase_aliases() -> None:
    route = respx.post(f"{BASE}/api/v2/transcripts/search").mock(
        return_value=httpx.Response(
            200,
            json=video_list(
                [
                    {
                        "videoId": "z",
                        "url": "https://www.tiktok.com/@c/video/z",
                        "title": "Z",
                        "channel": "C",
                        "publishedAt": "2026-09-01T00:00:00Z",
                        "stats": {"plays": 1240000},
                    }
                ],
                None,
                platform="tiktok",
            ),
        )
    )
    with _client() as tf:
        page = tf.transcripts.search("hi", platform="tiktok")
    assert route.calls.last.request.content == b'{"query": "hi", "platform": "tiktok"}' or (
        json.loads(route.calls.last.request.content) == {"query": "hi", "platform": "tiktok"}
    )
    assert page.platform == "tiktok"
    v = page.videos[0]
    assert v.video_id == "z"
    assert v.url == "https://www.tiktok.com/@c/video/z"
    assert v.thumbnail_url is None
    assert v.channel == "C"
    assert v.published_at == "2026-09-01T00:00:00Z"
    assert v.stats is not None and v.stats.plays == 1240000


@respx.mock
def test_batch() -> None:
    route = respx.post(f"{BASE}/api/v2/transcripts/batch").mock(
        return_value=httpx.Response(200, json=BATCH_ENV)
    )
    with _client() as tf:
        res = tf.transcripts.batch(["a", "b", "c"])
    assert [r.video_id for r in res.results] == ["a", "b", "c"]
    assert res.results[0].outcome == "ok"
    assert res.results[0].source == "captions"
    assert res.results[0].channel == "Example Channel"
    assert res.results[0].duration == 61
    assert res.results[0].language == "en"
    assert res.results[0].thumbnail_url == "https://i.ytimg.com/vi/a/mqdefault.jpg"
    # A failed entry carries none of the metadata, and that is a None, not an error.
    assert res.results[1].channel is None
    # A failed entry carries the standard error block.
    assert res.results[1].outcome == "error"
    assert res.results[1].error is not None
    assert res.results[1].error.code == "private"
    assert res.results[1].error.number == 4001
    # A captionless entry escalated to audio: processing + a pollable job_id.
    assert res.results[2].outcome == "processing"
    assert res.results[2].job_id == "asr_batch_1"
    assert res.results[2].poll_url == "/api/v2/transcripts/jobs/asr_batch_1"
    body = json.loads(route.calls.last.request.content)
    assert body["videoIds"] == ["a", "b", "c"]
    assert "mode" not in body  # server default (auto) unless asked for


@respx.mock
def test_batch_mode_captions() -> None:
    route = respx.post(f"{BASE}/api/v2/transcripts/batch").mock(
        return_value=httpx.Response(200, json=BATCH_ENV)
    )
    with _client() as tf:
        tf.transcripts.batch(["a", "b", "c"], mode="captions")
    assert json.loads(route.calls.last.request.content)["mode"] == "captions"


@respx.mock
def test_health_is_unauthenticated() -> None:
    route = respx.get(f"{BASE}/api/v2/health").mock(return_value=httpx.Response(200, json=HEALTH))
    with _client() as tf:
        h = tf.health()
    assert h["status"] == "ok"
    assert "authorization" not in route.calls.last.request.headers


@respx.mock
def test_me_returns_balance() -> None:
    route = respx.get(f"{BASE}/api/v2/me").mock(return_value=httpx.Response(200, json=ME_ENV))
    with _client() as tf:
        me = tf.me()
    assert me.user_id == "user_1"
    assert me.credits == 250
    assert me.usage is not None and me.usage.credits_spent == 0
    assert route.calls.last.request.headers["authorization"] == "Bearer tf_test"


@respx.mock
def test_video_without_captions_returns_pollable_job() -> None:
    # A 202 carries kind="transcript_job" and no transcript body; it must not
    # blow up parsing, since polling is the documented path from here.
    respx.post(f"{BASE}/api/v2/transcripts/video").mock(
        return_value=httpx.Response(202, json=JOB_ACCEPTED_ENV)
    )
    respx.get(f"{BASE}/api/v2/transcripts/jobs/asr_1").mock(
        side_effect=[
            httpx.Response(200, json=JOB_PROCESSING_ENV),
            httpx.Response(200, json=JOB_DONE_ENV),
        ]
    )
    with _client() as tf:
        started = tf.transcripts.video("https://www.tiktok.com/@u/video/7137723462233555205")
        assert started.status == "processing"
        assert started.job_id == "asr_1"
        assert started.poll_url == "/api/v2/transcripts/jobs/asr_1"
        assert started.text is None

        assert tf.transcripts.job("asr_1").status == "processing"
        done = tf.transcripts.job("asr_1")

    assert done.status == "completed"
    assert done.text == "hello world"
    assert done.usage is not None and done.usage.balance == 96


@respx.mock
@respx.mock
def test_missing_api_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TRANSCRIPTFETCH_API_KEY", raising=False)
    with pytest.raises(ValueError):
        TranscriptFetch()


CHUNKED_ENV = {
    "ok": True,
    "request_id": "req_chunks",
    "data": {
        "kind": "transcript",
        "video_id": "abc",
        "url": "https://www.youtube.com/watch?v=abc",
        "platform": "youtube",
        "title": "Example",
        "text": "hello world",
        "segments": [],
        "markdown": "# Example\n\n[0:00](https://www.youtube.com/watch?v=abc&t=0s) hello world",
        "chunks": [
            {"index": 0, "text": "hello world", "start": 0.0, "end": 2.5,
             "url": "https://www.youtube.com/watch?v=abc&t=0s", "tokens": 2},
        ],
    },
}


@respx.mock
def test_video_sends_and_parses_llm_formats() -> None:
    route = respx.post(f"{BASE}/api/v2/transcripts/video").mock(
        return_value=httpx.Response(200, json=CHUNKED_ENV)
    )
    with _client() as tf:
        t = tf.transcripts.video("abc", markdown=True, chunks={"max_tokens": 800})

    body = json.loads(route.calls.last.request.content)
    assert body == {"video": "abc", "markdown": True, "chunks": {"max_tokens": 800}}
    assert t.markdown and t.markdown.startswith("# Example")
    assert len(t.chunks) == 1
    c = t.chunks[0]
    assert (c.index, c.start, c.end, c.tokens) == (0, 0.0, 2.5, 2)
    assert c.url == "https://www.youtube.com/watch?v=abc&t=0s"


@respx.mock
def test_video_omits_unset_formats_and_false_chunks() -> None:
    route = respx.post(f"{BASE}/api/v2/transcripts/video").mock(
        return_value=httpx.Response(200, json=VIDEO_ENV)
    )
    with _client() as tf:
        t = tf.transcripts.video("abc", chunks=False)
    assert json.loads(route.calls.last.request.content) == {"video": "abc"}
    assert t.chunks == [] and t.markdown is None


@respx.mock
def test_batch_sends_chunks_true() -> None:
    route = respx.post(f"{BASE}/api/v2/transcripts/batch").mock(
        return_value=httpx.Response(200, json=BATCH_ENV)
    )
    with _client() as tf:
        tf.transcripts.batch(["a", "b"], chunks=True)
    assert json.loads(route.calls.last.request.content) == {"videoIds": ["a", "b"], "chunks": True}
