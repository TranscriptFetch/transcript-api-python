"""The ``transcripts`` resource: video / channel / playlist / search / batch /
job, plus auto-paginating iterators. Sync (:class:`Transcripts`) and async
(:class:`AsyncTranscripts`) variants share the parsing helpers below.

``video`` and ``batch`` take any supported source (YouTube, TikTok, Instagram,
or a direct media file URL). ``channel`` and ``playlist`` take a YouTube,
TikTok or Instagram URL and detect the platform from it; ``search`` searches
YouTube unless ``platform`` says otherwise. Every listed row carries a ``url``
that ``video``/``batch`` accept as-is.
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Iterable, Iterator, Literal, Optional, Protocol

from .._transport import parse_usage as _usage
from ..models import ApiErrorBlock, BatchResponse, Transcript, VideoList

# ── Paths ────────────────────────────────────────────────────────────────────
_VIDEO = "/api/v2/transcripts/video"
_CHANNEL = "/api/v2/transcripts/channel"
_PLAYLIST = "/api/v2/transcripts/playlist"
_SEARCH = "/api/v2/transcripts/search"
_BATCH = "/api/v2/transcripts/batch"
_JOB = "/api/v2/transcripts/jobs/{job_id}"


# ── Requester protocols (avoid importing the client → no circular import) ─────
class _SyncRequester(Protocol):
    def _request(
        self,
        method: str,
        path: str,
        *,
        body: Optional[dict[str, Any]] = ...,
        idempotency_key: Optional[str] = ...,
        auth: bool = ...,
        idempotent: bool = ...,
    ) -> dict[str, Any]: ...


class _AsyncRequester(Protocol):
    async def _request(
        self,
        method: str,
        path: str,
        *,
        body: Optional[dict[str, Any]] = ...,
        idempotency_key: Optional[str] = ...,
        auth: bool = ...,
        idempotent: bool = ...,
    ) -> dict[str, Any]: ...


# ── Shared parsing ────────────────────────────────────────────────────────────
def _parse_transcript(env: dict[str, Any]) -> Transcript:
    # ``data`` is null while an async transcription job is still processing, so
    # fall back to {} rather than letting None reach the validator.
    model = Transcript.model_validate(env.get("data") or {})
    model.usage = _usage(env)
    for field in ("status", "job_id", "poll_url"):
        value = env.get(field)
        if isinstance(value, str):
            setattr(model, field, value)
    # A failed job answers 200 with ok:false and the error block beside data.
    raw_error = env.get("error")
    if isinstance(raw_error, dict):
        model.error = ApiErrorBlock.model_validate(raw_error)
    return model


def _parse_videolist(env: dict[str, Any]) -> VideoList:
    model = VideoList.model_validate(env.get("data", {}))
    model.usage = _usage(env)
    return model


def _parse_batch(env: dict[str, Any]) -> BatchResponse:
    model = BatchResponse.model_validate(env.get("data", {}))
    model.usage = _usage(env)
    return model


def _list_body(
    key: str,
    value: str,
    limit: Optional[int],
    cursor: Optional[str],
    platform: Optional[str] = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {key: value}
    if limit is not None:
        body["limit"] = limit
    if cursor is not None:
        body["cursor"] = cursor
    if platform is not None:
        body["platform"] = platform
    return body


# ── Sync ──────────────────────────────────────────────────────────────────────
class Transcripts:
    def __init__(self, client: _SyncRequester) -> None:
        self._c = client

    def video(
        self,
        video: str,
        *,
        mode: Optional[Literal["auto", "captions", "audio"]] = None,
        timestamps: Optional[bool] = None,
        callback_url: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Transcript:
        """Fetch a single transcript (text + timestamped segments).

        ``video`` is a YouTube, TikTok or Instagram URL, a direct media file
        URL, or a bare YouTube ID.

        When the source has no captions the API transcribes its audio and
        answers with a job instead: the returned
        :class:`~transcriptfetch.Transcript` then has ``status ==
        "processing"`` and a ``job_id`` to pass to :meth:`job`.
        """
        env = self._c._request(
            "POST",
            _VIDEO,
            body={
                k: v
                for k, v in {
                    "video": video,
                    "mode": mode,
                    "timestamps": timestamps,
                    "callback_url": callback_url,
                }.items()
                if v is not None
            },
            idempotent=True,
            idempotency_key=idempotency_key,
        )
        return _parse_transcript(env)

    def channel(
        self,
        channel: str,
        *,
        limit: Optional[int] = None,
        cursor: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> VideoList:
        """List a YouTube channel's videos (metadata only), one page."""
        env = self._c._request(
            "POST",
            _CHANNEL,
            body=_list_body("channel", channel, limit, cursor),
            idempotent=True,
            idempotency_key=idempotency_key,
        )
        return _parse_videolist(env)

    def playlist(
        self,
        playlist: str,
        *,
        limit: Optional[int] = None,
        cursor: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> VideoList:
        """List a YouTube playlist's videos (metadata only), one page."""
        env = self._c._request(
            "POST",
            _PLAYLIST,
            body=_list_body("playlist", playlist, limit, cursor),
            idempotent=True,
            idempotency_key=idempotency_key,
        )
        return _parse_videolist(env)

    def search(
        self,
        query: str,
        *,
        platform: Optional[str] = None,
        limit: Optional[int] = None,
        cursor: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> VideoList:
        """Keyword search, one page of results (metadata only).

        YouTube by default; pass ``platform`` ("tiktok" or "instagram") to
        search elsewhere. Every result's ``url`` is accepted by ``video()`` as-is.
        """
        env = self._c._request(
            "POST",
            _SEARCH,
            body=_list_body("query", query, limit, cursor, platform),
            idempotent=True,
            idempotency_key=idempotency_key,
        )
        return _parse_videolist(env)

    def batch(
        self,
        video_ids: Iterable[str],
        *,
        mode: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> BatchResponse:
        """Fetch up to 50 transcripts in one call (same inputs as :meth:`video`).

        ``mode`` controls where each entry's text may come from:

        - ``"auto"`` (the default) reads captions and transcribes the audio
          when there are none. Captionless entries come back with ``outcome ==
          "processing"`` and a ``job_id``, cost nothing on this call, and are
          charged on delivery at the audio rate. Re-send the same batch once
          they have finished and the text is returned normally — or poll each
          ``job_id`` via :meth:`job`.
        - ``"captions"`` reads an existing caption track only, so a captionless
          video fails as ``no_transcript`` — the behaviour batch had before
          audio fallback existed.

        (``"audio"`` is not accepted on batch.)
        """
        body: dict[str, Any] = {"videoIds": list(video_ids)}
        if mode is not None:
            body["mode"] = mode
        env = self._c._request(
            "POST",
            _BATCH,
            body=body,
            idempotent=True,
            idempotency_key=idempotency_key,
        )
        return _parse_batch(env)

    def job(self, job_id: str) -> Transcript:
        """Poll an audio-transcription job started by :meth:`video`.

        Free to call. Returns a transcript whose ``status`` is ``"processing"``
        (``text`` still empty) or ``"completed"``. A job that failed comes back
        as an error envelope, so it raises :class:`~transcriptfetch.APIError`
        rather than returning a transcript you would have to inspect.
        """
        env = self._c._request("GET", _JOB.format(job_id=job_id))
        return _parse_transcript(env)

    # Auto-paginating iterators ------------------------------------------------
    def iter_channel(self, channel: str, *, limit: Optional[int] = None) -> Iterator[Any]:
        return self._iter(self.channel, channel, limit)

    def iter_playlist(self, playlist: str, *, limit: Optional[int] = None) -> Iterator[Any]:
        return self._iter(self.playlist, playlist, limit)

    def iter_search(
        self, query: str, *, platform: Optional[str] = None, limit: Optional[int] = None
    ) -> Iterator[Any]:
        return self._iter(self.search, query, limit, platform=platform)

    def _iter(self, method: Any, value: str, limit: Optional[int], **extra: Any) -> Iterator[Any]:
        cursor: Optional[str] = None
        while True:
            page: VideoList = method(value, limit=limit, cursor=cursor, **extra)
            yield from page.videos
            if not page.next_cursor:
                return
            cursor = page.next_cursor


# ── Async ─────────────────────────────────────────────────────────────────────
class AsyncTranscripts:
    def __init__(self, client: _AsyncRequester) -> None:
        self._c = client

    async def video(
        self,
        video: str,
        *,
        mode: Optional[Literal["auto", "captions", "audio"]] = None,
        timestamps: Optional[bool] = None,
        callback_url: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Transcript:
        """Fetch a single transcript. See :meth:`Transcripts.video`."""
        env = await self._c._request(
            "POST",
            _VIDEO,
            body={
                k: v
                for k, v in {
                    "video": video,
                    "mode": mode,
                    "timestamps": timestamps,
                    "callback_url": callback_url,
                }.items()
                if v is not None
            },
            idempotent=True,
            idempotency_key=idempotency_key,
        )
        return _parse_transcript(env)

    async def channel(
        self,
        channel: str,
        *,
        limit: Optional[int] = None,
        cursor: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> VideoList:
        env = await self._c._request(
            "POST",
            _CHANNEL,
            body=_list_body("channel", channel, limit, cursor),
            idempotent=True,
            idempotency_key=idempotency_key,
        )
        return _parse_videolist(env)

    async def playlist(
        self,
        playlist: str,
        *,
        limit: Optional[int] = None,
        cursor: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> VideoList:
        env = await self._c._request(
            "POST",
            _PLAYLIST,
            body=_list_body("playlist", playlist, limit, cursor),
            idempotent=True,
            idempotency_key=idempotency_key,
        )
        return _parse_videolist(env)

    async def search(
        self,
        query: str,
        *,
        platform: Optional[str] = None,
        limit: Optional[int] = None,
        cursor: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> VideoList:
        env = await self._c._request(
            "POST",
            _SEARCH,
            body=_list_body("query", query, limit, cursor, platform),
            idempotent=True,
            idempotency_key=idempotency_key,
        )
        return _parse_videolist(env)

    async def batch(
        self,
        video_ids: Iterable[str],
        *,
        mode: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> BatchResponse:
        """Fetch up to 50 transcripts in one call. See :meth:`Transcripts.batch`
        for the ``mode`` semantics (``"auto"`` transcribes captionless entries
        from audio and returns them as ``outcome == "processing"`` jobs;
        ``"captions"`` keeps the old captions-only behaviour)."""
        body: dict[str, Any] = {"videoIds": list(video_ids)}
        if mode is not None:
            body["mode"] = mode
        env = await self._c._request(
            "POST",
            _BATCH,
            body=body,
            idempotent=True,
            idempotency_key=idempotency_key,
        )
        return _parse_batch(env)

    async def job(self, job_id: str) -> Transcript:
        """Poll an audio-transcription job. See :meth:`Transcripts.job`."""
        env = await self._c._request("GET", _JOB.format(job_id=job_id))
        return _parse_transcript(env)

    async def iter_channel(
        self, channel: str, *, limit: Optional[int] = None
    ) -> AsyncIterator[Any]:
        async for v in self._iter(self.channel, channel, limit):
            yield v

    async def iter_playlist(
        self, playlist: str, *, limit: Optional[int] = None
    ) -> AsyncIterator[Any]:
        async for v in self._iter(self.playlist, playlist, limit):
            yield v

    async def iter_search(self, query: str, *, limit: Optional[int] = None) -> AsyncIterator[Any]:
        async for v in self._iter(self.search, query, limit):
            yield v

    async def _iter(
        self, method: Any, value: str, limit: Optional[int], **extra: Any
    ) -> AsyncIterator[Any]:
        cursor: Optional[str] = None
        while True:
            page: VideoList = await method(value, limit=limit, cursor=cursor, **extra)
            for v in page.videos:
                yield v
            if not page.next_cursor:
                return
            cursor = page.next_cursor
