"""Asynchronous TranscriptFetch client."""

from __future__ import annotations

import asyncio
from types import TracebackType
from typing import Any, Optional

import httpx

from ._config import resolve_config
from ._transport import (
    backoff_seconds,
    build_headers,
    is_retryable,
    new_idempotency_key,
    parse_envelope,
    parse_usage,
)
from .errors import APIConnectionError, APITimeoutError
from .models import Account
from .resources.monitors import AsyncMonitors
from .resources.transcripts import AsyncTranscripts


class AsyncTranscriptFetch:
    """Asynchronous client for the TranscriptFetch API.

    >>> import asyncio
    >>> from transcriptfetch import AsyncTranscriptFetch
    >>> async def main() -> None:
    ...     async with AsyncTranscriptFetch(api_key="tf_live_...") as tf:
    ...         t = await tf.transcripts.video("dQw4w9WgXcQ")
    ...         print(t.text)
    >>> asyncio.run(main())
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 2,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self._config = resolve_config(api_key, base_url, timeout, max_retries)
        self._owns_http = http_client is None
        self._http = http_client or httpx.AsyncClient(
            base_url=self._config.base_url, timeout=self._config.timeout
        )
        self.monitors = AsyncMonitors(self)
        self.transcripts = AsyncTranscripts(self)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        body: Optional[dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
        auth: bool = True,
        idempotent: bool = False,
    ) -> dict[str, Any]:
        key = idempotency_key
        if idempotent and key is None:
            key = new_idempotency_key()
        headers = build_headers(self._config, key, needs_key=auth)

        attempt = 0
        while True:
            try:
                resp = await self._http.request(method, path, json=body, headers=headers)
            except httpx.TimeoutException as exc:
                raise APITimeoutError(str(exc)) from exc
            except httpx.HTTPError as exc:
                raise APIConnectionError(str(exc)) from exc

            if is_retryable(resp.status_code) and attempt < self._config.max_retries:
                await asyncio.sleep(backoff_seconds(attempt, resp.headers.get("retry-after")))
                attempt += 1
                continue
            return parse_envelope(resp)

    async def me(self) -> Account:
        """Validate the API key and read the account's credit balance. Free."""
        env = await self._request("GET", "/api/v2/me")
        account = Account.model_validate(env.get("data") or {})
        account.usage = parse_usage(env)
        return account

    async def health(self) -> dict[str, Any]:
        """Unauthenticated liveness probe."""
        return await self._request("GET", "/api/v2/health", auth=False)

    async def close(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def __aenter__(self) -> "AsyncTranscriptFetch":
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        await self.close()
