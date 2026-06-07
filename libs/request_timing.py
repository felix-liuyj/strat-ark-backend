"""Request timing helpers for targeted API diagnostics."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from fastapi import Request, Response

__all__ = (
    "attach_server_timing_header",
    "get_request_timings",
    "record_request_timing",
    "should_trace_request",
)

_REQUEST_TIMINGS_STATE_KEY = "_request_timings"
_TRACED_PATHS = frozenset(
    {
        "/rules/filler-specs",
    }
)


def should_trace_request(request: Request) -> bool:
    return request.url.path in _TRACED_PATHS


def _normalize_metric_name(name: str) -> str:
    return "".join(ch for ch in name if ch.isalnum() or ch in ("-", "_")) or "metric"


def get_request_timings(request: Request) -> Sequence[dict[str, Any]]:
    timings = getattr(request.state, _REQUEST_TIMINGS_STATE_KEY, None)
    if timings is None:
        timings = []
        setattr(request.state, _REQUEST_TIMINGS_STATE_KEY, timings)
    return timings


def record_request_timing(request: Request, name: str, duration_ms: float) -> None:
    if not should_trace_request(request):
        return

    timings = get_request_timings(request)
    timings.append(
        {
            "name": _normalize_metric_name(name),
            "durationMs": round(duration_ms, 3),
        }
    )


def attach_server_timing_header(request: Request, response: Response) -> None:
    if not should_trace_request(request):
        return

    timings = get_request_timings(request)
    if not timings:
        return

    response.headers["Server-Timing"] = ", ".join(f"{item['name']};dur={item['durationMs']:.3f}" for item in timings)
