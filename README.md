<p align="center">
  <img src="https://raw.githubusercontent.com/TranscriptFetch/transcript-api-python/main/assets/logo.png" alt="TranscriptFetch" width="84" height="84" />
</p>

# TranscriptFetch Python SDK

Official, typed Python client for the [TranscriptFetch](https://transcriptfetch.com) API: fetch transcripts as clean, structured data, plus channel, playlist and search listings across YouTube, TikTok and Instagram. Sync + async, fully type-hinted.

Transcripts come from **YouTube, TikTok, Instagram, or a direct media file URL** (mp3/mp4/wav and friends). Channel and playlist take a URL from any of those platforms and detect it; search is YouTube by default, or any of them via `platform=`.

```bash
pip install transcriptfetch-sdk
```

## Quickstart

```python
from transcriptfetch import TranscriptFetch

# api_key falls back to the TRANSCRIPTFETCH_API_KEY env var
tf = TranscriptFetch(api_key="tf_live_...")

t = tf.transcripts.video("https://youtu.be/aircAruvnKk")   # or a TikTok / Instagram / file URL
print(t.title)
print(t.text)
for seg in t.segments:
    print(f"[{seg.start:.1f}] {seg.text}")

print("credits left:", t.usage.balance)
```

Every transcript carries the same metadata whichever platform served it:
`video_id`, `url`, `platform`, `title`, `channel` (the creator), `duration` in
seconds, `language`, `thumbnail_url` and `source` (`"captions"` or `"audio"`).
A value the API could not determine is `None`, never missing.

Get an API key (50 free credits) at <https://transcriptfetch.com/app>. One credit per successful fetch; failed/blocked/no-transcript requests are free.

## Endpoints

```python
tf.transcripts.video(video)                        # single transcript (text + segments)
tf.transcripts.batch(video_ids, mode=)             # up to 50 transcripts in one call
tf.transcripts.channel(channel, limit=, cursor=)   # a channel's or creator's videos (metadata)
tf.transcripts.playlist(playlist, limit=, cursor=) # a playlist's videos
tf.transcripts.search(query, platform=, limit=, cursor=)  # keyword search, YouTube by default
tf.transcripts.job(job_id)                         # poll an audio-transcription job (free)
tf.me()                                            # validate the key + read the balance (free)
tf.health()                                        # unauthenticated liveness probe
```

`video` and `batch` take a YouTube, TikTok or Instagram URL, a direct media file URL, or a bare YouTube ID. `channel`/`playlist` take a YouTube, TikTok or Instagram URL (or a YouTube `@handle` / `PL…` id) and detect the platform from it. `search` searches YouTube unless you pass `platform`:

```python
page = tf.transcripts.search("lofi hip hop", platform="tiktok", limit=10)
for v in page.videos:
    print(v.title, v.published_at, v.stats.plays if v.stats else None)
    t = tf.transcripts.video(v.url)
```

## Sources without captions

When a source has no captions, the API transcribes its audio and answers with a job instead of a transcript. That comes back as a `Transcript` with `status == "processing"` and a `job_id`; poll it for free until it completes.

```python
import time

t = tf.transcripts.video("https://www.tiktok.com/@user/video/7137723462233555205")
while t.status == "processing":
    time.sleep(3)
    t = tf.transcripts.job(t.job_id)
print(t.text)
```

Batch works the same way by default (`mode="auto"`): entries with no caption track are transcribed from audio, come back with `outcome == "processing"` and a `job_id`, cost nothing on that call, and are charged on delivery at the audio rate. Re-send the same batch once the jobs have had time to finish and the text comes back normally — or poll each `job_id` with `tf.transcripts.job()`. Pass `mode="captions"` to read existing caption tracks only, in which case a captionless video fails as `outcome == "error"` with `error.code == "no_captions"` (and `error.retry_with` naming the audio mode):

```python
res = tf.transcripts.batch(ids)                    # captionless entries -> "processing" + job_id
pending = [r.job_id for r in res.results if r.outcome == "processing"]

res = tf.transcripts.batch(ids, mode="captions")   # captions only, no audio fallback
```

## Monitors (2.4.0+)

Watch a YouTube channel or a TikTok/Instagram profile for new videos. Creation
reads the target once to record what is already there (existing videos are
skipped) and starts scheduled checks. Every check costs 1 credit whether or not
it finds new videos, and so does that first read; caption transcripts cost 1
credit more each when enabled. A check whose listing fails is free. See
[monitor docs](https://transcriptfetch.com/docs/monitors) for plan limits, audio
billing, retention and webhook verification.

```python
with TranscriptFetch(timeout=120) as tf:
    monitor = tf.monitors.create("@lexfridman", interval_minutes=60, transcripts=True)
    # Save monitor.webhook_secret securely: it is only returned on creation.
    # Optional webhook_url="https://your-app.com/hooks/transcriptfetch".
    # YouTube only: tab="shorts" (or "videos" / "live").
    all_monitors = tf.monitors.list()
    news = tf.monitors.list(since=all_monitors.last_event_id)
    current = tf.monitors.get(monitor.id)
    page = tf.monitors.events(monitor.id, limit=10)
    for event in tf.monitors.iter_events(monitor.id, since=current.last_event_id):
        print(event.type, event.data)
    tf.monitors.update(monitor.id, status="paused")
    tf.monitors.update(monitor.id, webhook_url=None, name=None, transcripts=False)
    # Omitted settings stay unchanged. None clears webhook_url/name.
    tf.monitors.update(monitor.id, status="active")
    checked = tf.monitors.check(monitor.id)  # 1 credit, found or not
    if checked.error:  # listing failure, even with HTTP 200
        print(checked.error)
    tf.monitors.delete(monitor.id)  # removes events too
```

`AsyncTranscriptFetch` exposes the same methods with `await`; use `async for`
with `tf.monitors.iter_events(...)`. Models use snake_case. `monitor.videos`
events carry `data.videos` and optional `data.transcripts` with `ok`, `processing`
or `error` outcomes. `monitor.transcript` events carry the follow-up result
in `data`, linked to the parent via `videos_event_id`. `delivery` describes
webhook attempts. Reading never marks events read: persist the latest event id
and pass it as `since`. Iteration preserves `since` across cursor pages.
Create/check accept `idempotency_key`; the generated key stays stable on retries.
Use a longer client timeout for creation/manual checks, which read the platform.

Single-video options are also supported:

```python
transcript = tf.transcripts.video("dQw4w9WgXcQ", mode="captions", timestamps=False)
```

## Pagination

List endpoints are cursor-paginated. Iterate every result without managing cursors:

```python
for video in tf.transcripts.iter_channel("@lexfridman", limit=10):
    print(video.video_id, video.title)
```

Or page manually via `page.next_cursor` and the `cursor=` argument.

## Async

```python
import asyncio
from transcriptfetch import AsyncTranscriptFetch

async def main():
    async with AsyncTranscriptFetch() as tf:
        t = await tf.transcripts.video("aircAruvnKk")
        print(t.text)
        async for v in tf.transcripts.iter_search("how transformers work", limit=10):
            print(v.title)

asyncio.run(main())
```

## Errors

All errors subclass `TranscriptFetchError`. API errors carry `.status`, `.code`, `.number` (the thousands digit is the family; 5xxx means retry), `.message`, `.docs`, `.retry_with` (the request change that would succeed, when there is one), `.details`, `.request_id`, and a `.retryable` property:

```python
from transcriptfetch import (
    AuthenticationError, InsufficientCreditsError, InvalidRequestError,
    RateLimitError, IdempotencyConflictError, UpstreamUnavailableError,
    InternalServerError, APIError, APIConnectionError, APITimeoutError,
)

try:
    tf.transcripts.video("bad")
except InsufficientCreditsError:
    ...                       # 402: top up at /pricing
except RateLimitError as e:
    print(e.retry_after)      # 429
except APIError as e:
    print(e.status, e.code, e.request_id)
```

## Reliability

- **Automatic retries** on `429` (honoring `Retry-After`) and `5xx`, with exponential backoff + jitter (`max_retries=2` by default).
- **Idempotency**: every write auto-sends an `Idempotency-Key` so a retried request is never double-charged. Override per call with `idempotency_key=...`.
- **Configurable:** `TranscriptFetch(api_key=..., base_url=..., timeout=30, max_retries=2)`. Both clients are context managers and accept a custom `http_client=` (httpx).

## Development

```bash
pip install -e ".[dev]"
ruff check . && mypy src && pytest
```

Tests are fully mocked (no network). MIT licensed.
