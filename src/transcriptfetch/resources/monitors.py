"""Scheduled channel/profile monitors. Sync and async share request/response helpers."""

from __future__ import annotations

from typing import Any, AsyncIterator, Iterator, Literal, Optional, Union
from urllib.parse import quote, urlencode

from .._transport import parse_usage
from ..models import (
    Monitor,
    MonitorCheck,
    MonitorDeleted,
    MonitorEvent,
    MonitorEventList,
    MonitorInterval,
    MonitorList,
)
from .transcripts import _AsyncRequester, _SyncRequester


class _Unset:
    pass


_UNSET = _Unset()
_BASE = "/api/v2/monitors"


def _path(monitor_id: str) -> str:
    return f"{_BASE}/{quote(monitor_id, safe='')}"


def _query(**values: Any) -> str:
    encoded = urlencode({key: value for key, value in values.items() if value is not None})
    return f"?{encoded}" if encoded else ""


def _settings(**values: Any) -> dict[str, Any]:
    # None clears webhook_url/name. Omitted fields leave their values unchanged.
    return {key: value for key, value in values.items() if not isinstance(value, _Unset)}


def _monitor(env: dict[str, Any]) -> Monitor:
    result = Monitor.model_validate(env["data"])
    result.usage = parse_usage(env)
    return result


def _check(env: dict[str, Any]) -> MonitorCheck:
    result = MonitorCheck.model_validate(env["data"])
    result.usage = parse_usage(env)
    return result


class Monitors:
    def __init__(self, client: _SyncRequester) -> None:
        self._c = client

    def create(
        self,
        target: str,
        *,
        type: Literal["channel"] = "channel",
        platform: Optional[Literal["youtube", "tiktok", "instagram"]] = None,
        tab: Optional[Literal["videos", "shorts", "live"]] = None,
        webhook_url: Optional[str] = None,
        interval_minutes: Optional[MonitorInterval] = None,
        transcripts: Optional[bool] = None,
        name: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Monitor:
        """Create a scheduled monitor. Save webhook_secret: it is only returned here.

        Creation reads the target once (1 credit) and skips the videos already
        there. Every later check costs 1 credit whether or not it finds new
        videos. tab selects a YouTube uploads/Shorts/live feed only.
        """
        body = {
            key: value
            for key, value in {
                "target": target,
                "type": type,
                "platform": platform,
                "tab": tab,
                "webhook_url": webhook_url,
                "interval_minutes": interval_minutes,
                "transcripts": transcripts,
                "name": name,
            }.items()
            if value is not None
        }
        env = self._c._request(
            "POST", _BASE, body=body, idempotent=True, idempotency_key=idempotency_key
        )
        return _monitor(env)

    def list(self, *, since: Optional[str] = None) -> MonitorList:
        """All account monitors. Free. since is the last_event_id previously seen."""
        env = self._c._request("GET", _BASE + _query(since=since))
        return MonitorList.model_validate(env["data"])

    def get(self, monitor_id: str, *, since: Optional[str] = None) -> Monitor:
        """Read settings and news, without marking anything read. Free."""
        return _monitor(self._c._request("GET", _path(monitor_id) + _query(since=since)))

    def update(
        self,
        monitor_id: str,
        *,
        webhook_url: Union[str, None, _Unset] = _UNSET,
        interval_minutes: Union[MonitorInterval, _Unset] = _UNSET,
        transcripts: Union[bool, _Unset] = _UNSET,
        name: Union[str, None, _Unset] = _UNSET,
        status: Union[Literal["active", "paused"], _Unset] = _UNSET,
    ) -> Monitor:
        """Change supplied fields only. None clears webhook_url/name; False disables transcripts.

        status="paused" stops scheduled checks, "active" resumes. Free.
        """
        body = _settings(
            webhook_url=webhook_url,
            interval_minutes=interval_minutes,
            transcripts=transcripts,
            name=name,
            status=status,
        )
        return _monitor(self._c._request("PATCH", _path(monitor_id), body=body))

    def delete(self, monitor_id: str) -> MonitorDeleted:
        """Delete the monitor/events. Already-running transcription jobs may still bill."""
        env = self._c._request("DELETE", _path(monitor_id))
        return MonitorDeleted.model_validate(env["data"])

    def check(self, monitor_id: str, *, idempotency_key: Optional[str] = None) -> MonitorCheck:
        """Check now, even when paused: 1 credit, found or not. Inspect result.error."""
        env = self._c._request(
            "POST", _path(monitor_id) + "/check", idempotent=True, idempotency_key=idempotency_key
        )
        return _check(env)

    def events(
        self,
        monitor_id: str,
        *,
        limit: Optional[int] = None,
        cursor: Optional[str] = None,
        since: Optional[str] = None,
    ) -> MonitorEventList:
        """One page of events, newest first. Free. since limits results to newer events."""
        env = self._c._request(
            "GET", _path(monitor_id) + "/events" + _query(limit=limit, cursor=cursor, since=since)
        )
        return MonitorEventList.model_validate(env["data"])

    def iter_events(
        self,
        monitor_id: str,
        *,
        limit: Optional[int] = None,
        cursor: Optional[str] = None,
        since: Optional[str] = None,
    ) -> Iterator[MonitorEvent]:
        """Iterate events, preserving since across cursor pages. Free."""
        while True:
            page = self.events(monitor_id, limit=limit, cursor=cursor, since=since)
            yield from page.events
            if not page.next_cursor:
                return
            cursor = page.next_cursor


class AsyncMonitors:
    def __init__(self, client: _AsyncRequester) -> None:
        self._c = client

    async def create(
        self,
        target: str,
        *,
        type: Literal["channel"] = "channel",
        platform: Optional[Literal["youtube", "tiktok", "instagram"]] = None,
        tab: Optional[Literal["videos", "shorts", "live"]] = None,
        webhook_url: Optional[str] = None,
        interval_minutes: Optional[MonitorInterval] = None,
        transcripts: Optional[bool] = None,
        name: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Monitor:
        """Create a scheduled monitor. Save webhook_secret: it is only returned here.

        Creation reads the target once (1 credit) and skips the videos already
        there. Every later check costs 1 credit whether or not it finds new
        videos. tab selects a YouTube uploads/Shorts/live feed only.
        """
        body = {
            key: value
            for key, value in {
                "target": target,
                "type": type,
                "platform": platform,
                "tab": tab,
                "webhook_url": webhook_url,
                "interval_minutes": interval_minutes,
                "transcripts": transcripts,
                "name": name,
            }.items()
            if value is not None
        }
        env = await self._c._request(
            "POST", _BASE, body=body, idempotent=True, idempotency_key=idempotency_key
        )
        return _monitor(env)

    async def list(self, *, since: Optional[str] = None) -> MonitorList:
        """All account monitors. Free. since is the last_event_id previously seen."""
        env = await self._c._request("GET", _BASE + _query(since=since))
        return MonitorList.model_validate(env["data"])

    async def get(self, monitor_id: str, *, since: Optional[str] = None) -> Monitor:
        """Read settings and news, without marking anything read. Free."""
        return _monitor(await self._c._request("GET", _path(monitor_id) + _query(since=since)))

    async def update(
        self,
        monitor_id: str,
        *,
        webhook_url: Union[str, None, _Unset] = _UNSET,
        interval_minutes: Union[MonitorInterval, _Unset] = _UNSET,
        transcripts: Union[bool, _Unset] = _UNSET,
        name: Union[str, None, _Unset] = _UNSET,
        status: Union[Literal["active", "paused"], _Unset] = _UNSET,
    ) -> Monitor:
        """Change supplied fields only. None clears webhook_url/name; False disables transcripts.

        status="paused" stops scheduled checks, "active" resumes. Free.
        """
        body = _settings(
            webhook_url=webhook_url,
            interval_minutes=interval_minutes,
            transcripts=transcripts,
            name=name,
            status=status,
        )
        return _monitor(await self._c._request("PATCH", _path(monitor_id), body=body))

    async def delete(self, monitor_id: str) -> MonitorDeleted:
        """Delete the monitor/events. Already-running transcription jobs may still bill."""
        env = await self._c._request("DELETE", _path(monitor_id))
        return MonitorDeleted.model_validate(env["data"])

    async def check(
        self, monitor_id: str, *, idempotency_key: Optional[str] = None
    ) -> MonitorCheck:
        """Check now, even when paused: 1 credit, found or not. Inspect result.error."""
        env = await self._c._request(
            "POST", _path(monitor_id) + "/check", idempotent=True, idempotency_key=idempotency_key
        )
        return _check(env)

    async def events(
        self,
        monitor_id: str,
        *,
        limit: Optional[int] = None,
        cursor: Optional[str] = None,
        since: Optional[str] = None,
    ) -> MonitorEventList:
        """One page of events, newest first. Free. since limits results to newer events."""
        env = await self._c._request(
            "GET", _path(monitor_id) + "/events" + _query(limit=limit, cursor=cursor, since=since)
        )
        return MonitorEventList.model_validate(env["data"])

    async def iter_events(
        self,
        monitor_id: str,
        *,
        limit: Optional[int] = None,
        cursor: Optional[str] = None,
        since: Optional[str] = None,
    ) -> AsyncIterator[MonitorEvent]:
        """Iterate events, preserving since across cursor pages. Free."""
        while True:
            page = await self.events(monitor_id, limit=limit, cursor=cursor, since=since)
            for event in page.events:
                yield event
            if not page.next_cursor:
                return
            cursor = page.next_cursor
