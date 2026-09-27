"""Typed response models (Pydantic v2), matching the TranscriptFetch API schemas.

The API mixes snake_case (transcript/list envelopes) and camelCase (video list
items). We normalize everything to snake_case attributes via field aliases, while
still accepting the wire names on input.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Model(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")


class Usage(_Model):
    """Credit + byte accounting returned alongside every successful response."""

    credits_spent: int = 0
    balance: Optional[int] = None  # null for unlimited (admin) accounts
    bytes: int = 0


class Segment(_Model):
    """A single timestamped caption cue.

    ``speaker`` is set only when the API ran speaker diarization on an audio
    transcription: a small integer (0, 1, …) identifying who is talking. The
    ids are hints from voice separation, not named identification.
    """

    start: float = 0.0
    duration: float = 0.0
    text: str = ""
    speaker: Optional[int] = None


class Transcript(_Model):
    """A single video's transcript, from any supported source.

    Also covers the "not ready yet" case. When a video has no captions the API
    transcribes the audio and answers 202 with ``kind == "transcript_job"``,
    which is why ``kind`` is a plain ``str``: pinning it to a literal would turn
    a 202 into a validation error instead of a pollable job. In that case
    ``text``/``segments`` are empty and ``status``/``job_id`` are set, so pass
    ``job_id`` to ``transcripts.job()`` until ``status == "completed"``.

    Every metadata field (``video_id``, ``url``, ``platform``, ``title``,
    ``channel``, ``duration``, ``language``, ``thumbnail_url``, ``source``) is
    present on every transcript, whichever platform or path served it; ``None``
    means the API could not determine it, never that it was left out (API
    contract of 2026-09-15).
    """

    kind: str = "transcript"
    video_id: str = ""
    platform: Optional[str] = None  # youtube | tiktok | instagram | file
    title: Optional[str] = None
    url: Optional[str] = None
    """Canonical URL of the item, when known. Accepted as-is by ``transcripts.video()``."""
    channel: Optional[str] = None
    """The creator, as the platform names them: a YouTube channel name, a TikTok
    @handle, an Instagram username, the uploader for a file."""
    duration: Optional[float] = None
    """Media length in seconds, when the source reports it."""
    language: Optional[str] = None
    """The caption track's language code, or the language detected during AI transcription."""
    thumbnail_url: Optional[str] = Field(default=None, alias="thumbnailUrl")
    """Poster image. TikTok and Instagram serve signed, expiring URLs, so copy
    the image rather than hotlinking it."""
    source: Optional[str] = None  # "captions" | "audio" (AI transcription); None on a 202
    text: Optional[str] = None
    segments: List[Segment] = Field(default_factory=list)
    usage: Optional[Usage] = None
    # Envelope-level fields, lifted onto the model so an async job round-trips
    # as one object (the API returns them beside ``data``, not inside it).
    status: Optional[str] = None  # "processing" | "completed" | "failed", async jobs only
    job_id: Optional[str] = None
    poll_url: Optional[str] = None
    error: Optional["ApiErrorBlock"] = None
    """Why a job failed. Set only when ``status == "failed"``."""

    @field_validator("segments", mode="before")
    @classmethod
    def _null_segments_to_list(cls, v: Any) -> Any:
        return v or []


class Account(_Model):
    """The calling key's account (``kind == "me"``): identity + credit balance."""

    kind: Literal["me"] = "me"
    user_id: str = ""
    credits: Optional[int] = None  # null for unlimited (admin) accounts
    usage: Optional[Usage] = None


class VideoStats(_Model):
    """Engagement counts on a list row, where the source exposes them."""

    plays: Optional[int] = None


class Video(_Model):
    """A video reference from a channel/playlist/search list (metadata only).

    ``url`` is accepted as-is by ``transcripts.video()`` and ``batch()``,
    whatever the platform. The platform is not repeated per row:
    ``VideoList.platform`` says it. ``published_at`` is exact for TikTok,
    Instagram and approximate on YouTube, whose listings only
    say "2 days ago" (exact to the day for recent videos, up to a year off
    for old ones). ``thumbnail_url`` is always ``None`` on v2: the API stopped
    sending poster images on 2026-09-08.
    """

    video_id: str = Field(alias="videoId")
    url: Optional[str] = None
    title: Optional[str] = None
    thumbnail_url: Optional[str] = Field(default=None, alias="thumbnailUrl")
    duration: Optional[float] = None
    channel: Optional[str] = None
    published_at: Optional[str] = Field(default=None, alias="publishedAt")
    stats: Optional[VideoStats] = None


class VideoList(_Model):
    """A paginated list of videos (``kind == "video_list"``).

    ``platform`` is where the rows came from: the ``platform`` argument on
    search, the platform detected from the URL on channel and playlist.
    """

    kind: Literal["video_list"] = "video_list"
    source: str = ""
    platform: Optional[str] = None  # youtube | tiktok | instagram
    videos: List[Video] = Field(default_factory=list)
    next_cursor: Optional[str] = None
    usage: Optional[Usage] = None


class ApiErrorBlock(_Model):
    """The API's error block, as it appears on a failed batch entry or a
    failed job. Request-level failures raise :class:`APIError` with the same
    fields. ``number``'s thousands digit is the family; 5xxx means retry."""

    code: str = ""
    number: Optional[int] = None
    message: str = ""
    docs: Optional[str] = None
    retry_with: Optional[Dict[str, Any]] = None
    """The request change that would succeed, e.g. ``{"mode": "audio"}``."""
    details: Optional[Dict[str, Any]] = None


class BatchResult(_Model):
    """One video's result inside a batch response.

    Exactly three outcomes. ``"ok"`` carries the transcript (``text``,
    ``segments``, ``source``). ``"processing"`` carries the audio-transcription
    job started for a captionless entry (batch ``mode="auto"``): it costs
    nothing on that call and is charged on delivery at the audio rate; either
    re-send the same batch once the jobs have had time to finish or poll
    ``job_id`` via ``transcripts.job()``. ``"error"`` carries the same error
    block a request-level failure raises, in ``error``. Send
    ``mode="captions"`` to have captionless entries fail as ``"error"`` with
    code ``no_captions`` (and ``error.retry_with`` naming the audio mode).
    """

    video_id: str = ""
    outcome: str = "error"  # ok | processing | error
    error: Optional[ApiErrorBlock] = None
    title: Optional[str] = None
    url: Optional[str] = None
    """Canonical URL of the item, when known. Accepted as-is by ``transcripts.video()``."""
    channel: Optional[str] = None
    """The creator, as the platform names them: a YouTube channel name, a TikTok
    @handle, an Instagram username, the uploader for a file."""
    duration: Optional[float] = None
    """Media length in seconds, when the source reports it."""
    language: Optional[str] = None
    """The caption track's language code, or the language detected during AI transcription."""
    thumbnail_url: Optional[str] = Field(default=None, alias="thumbnailUrl")
    """Poster image. TikTok and Instagram serve signed, expiring URLs, so copy
    the image rather than hotlinking it."""
    source: Optional[str] = None  # "captions" | "audio" on outcome "ok"
    text: Optional[str] = None
    segments: Optional[List[Segment]] = None
    job_id: Optional[str] = None
    """Set when ``outcome == "processing"``: the audio-transcription job that
    will deliver this entry."""
    poll_url: Optional[str] = None
    bytes: int = 0


class BatchResponse(_Model):
    """Result of a batch fetch (``kind == "transcript_batch"``)."""

    kind: Literal["transcript_batch"] = "transcript_batch"
    results: List[BatchResult] = Field(default_factory=list)
    usage: Optional[Usage] = None


# Monitor response models -----------------------------------------------------
MonitorInterval = Literal[15, 60, 360, 1440]


class MonitorSnapshot(_Model):
    id: str
    name: Optional[str] = None
    type: str = "channel"
    platform: str = "youtube"
    target: str = ""


class MonitorLastError(ApiErrorBlock):
    at: Optional[str] = None


class Monitor(MonitorSnapshot):
    """A scheduled monitor. webhook_secret and baseline_count appear only on creation."""

    kind: str = "monitor"
    options: Dict[str, Any] = Field(default_factory=dict)
    status: str = "active"
    has_new: bool = False
    last_event_id: Optional[str] = None
    interval_minutes: int = 60
    transcripts: bool = False
    webhook_url: Optional[str] = None
    next_check_at: Optional[str] = None
    last_checked_at: Optional[str] = None
    last_error: Optional[MonitorLastError] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    webhook_secret: Optional[str] = Field(default=None, repr=False)
    baseline_count: Optional[int] = None
    usage: Optional[Usage] = None


class MonitorLimits(_Model):
    max_monitors: Optional[int] = None
    min_interval_minutes: int = 60


class MonitorList(_Model):
    kind: str = "monitor_list"
    monitors: List[Monitor] = Field(default_factory=list)
    has_new: bool = False
    last_event_id: Optional[str] = None
    limits: MonitorLimits = Field(default_factory=MonitorLimits)


class MonitorDeleted(_Model):
    kind: str = "monitor_deleted"
    id: str


class MonitorDelivery(_Model):
    status: str = "none"
    attempts: int = 0
    last_attempt_at: Optional[str] = None
    next_attempt_at: Optional[str] = None
    last_error: Optional[str] = None
    delivered_at: Optional[str] = None


class MonitorTranscriptResult(_Model):
    job_id: Optional[str] = None
    video_id: str
    url: str = ""
    outcome: str
    transcript: Optional[Transcript] = None
    error: Optional[ApiErrorBlock] = None


class MonitorVideosData(_Model):
    videos: List[Video] = Field(default_factory=list)
    transcripts: Optional[List[MonitorTranscriptResult]] = None


class MonitorTranscriptData(MonitorTranscriptResult):
    videos_event_id: str


class MonitorVideosEvent(_Model):
    id: str
    type: Literal["monitor.videos"]
    created_at: str
    monitor: MonitorSnapshot
    credits_spent: int = 0
    data: MonitorVideosData
    delivery: Optional[MonitorDelivery] = None


class MonitorTranscriptEvent(_Model):
    id: str
    type: Literal["monitor.transcript"]
    created_at: str
    monitor: MonitorSnapshot
    credits_spent: int = 0
    data: MonitorTranscriptData
    delivery: Optional[MonitorDelivery] = None


MonitorEvent = Union[MonitorVideosEvent, MonitorTranscriptEvent]


class MonitorEventList(_Model):
    kind: str = "monitor_event_list"
    monitor_id: str
    events: List[MonitorEvent] = Field(default_factory=list)
    next_cursor: Optional[str] = None


class MonitorCheck(_Model):
    """A check may return HTTP 200 with error set when the listing failed."""

    kind: str = "monitor_check"
    monitor: Monitor
    new_videos: int = 0
    event: Optional[MonitorEvent] = None
    error: Optional[ApiErrorBlock] = None
    usage: Optional[Usage] = None
