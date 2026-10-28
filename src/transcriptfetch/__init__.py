"""Official Python SDK for the TranscriptFetch API.

from transcriptfetch import TranscriptFetch

tf = TranscriptFetch(api_key="tf_live_...")   # or set TRANSCRIPTFETCH_API_KEY
t = tf.transcripts.video("dQw4w9WgXcQ")
print(t.text, t.usage.balance)
"""

from __future__ import annotations

from ._version import __version__
from .async_client import AsyncTranscriptFetch
from .client import TranscriptFetch
from .errors import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AuthenticationError,
    BatchTooLargeError,
    IdempotencyConflictError,
    InsufficientCreditsError,
    InternalServerError,
    InvalidRequestError,
    NotFoundError,
    RateLimitError,
    TranscriptFetchError,
    UnprocessableInputError,
    UpstreamUnavailableError,
)
from .models import (
    Account,
    ApiErrorBlock,
    BatchResponse,
    BatchResult,
    Chunk,
    Monitor,
    MonitorCheck,
    MonitorDeleted,
    MonitorDelivery,
    MonitorEvent,
    MonitorEventList,
    MonitorInterval,
    MonitorLastError,
    MonitorLimits,
    MonitorList,
    MonitorSnapshot,
    MonitorTranscriptData,
    MonitorTranscriptEvent,
    MonitorTranscriptResult,
    MonitorVideosData,
    MonitorVideosEvent,
    Segment,
    Transcript,
    Usage,
    Video,
    VideoList,
    VideoStats,
)
from .resources.transcripts import ChunkOptions

__all__ = [
    "__version__",
    "TranscriptFetch",
    "AsyncTranscriptFetch",
    "Monitor",
    "MonitorSnapshot",
    "MonitorLastError",
    "MonitorLimits",
    "MonitorList",
    "MonitorDeleted",
    "MonitorDelivery",
    "MonitorTranscriptResult",
    "MonitorVideosData",
    "MonitorTranscriptData",
    "MonitorVideosEvent",
    "MonitorTranscriptEvent",
    "MonitorEvent",
    "MonitorEventList",
    "MonitorCheck",
    "MonitorInterval",
    # models
    "Usage",
    "Account",
    "Chunk",
    "ChunkOptions",
    "Segment",
    "Transcript",
    "Video",
    "VideoStats",
    "VideoList",
    "ApiErrorBlock",
    "BatchResult",
    "BatchResponse",
    # errors
    "TranscriptFetchError",
    "APIError",
    "APIConnectionError",
    "APITimeoutError",
    "AuthenticationError",
    "InvalidRequestError",
    "BatchTooLargeError",
    "InsufficientCreditsError",
    "NotFoundError",
    "UnprocessableInputError",
    "IdempotencyConflictError",
    "RateLimitError",
    "UpstreamUnavailableError",
    "InternalServerError",
]
