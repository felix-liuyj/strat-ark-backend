"""HTTP client helpers with retry."""

import asyncio
from typing import Any

import httpx

__all__ = (
    "create_async_http_client",
    "request_with_retry",
)


def create_async_http_client(timeout: float = 15.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout)


async def request_with_retry(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    retries: int = 3,
    retry_interval: float = 0.5,
    timeout: float = 15.0,
) -> httpx.Response:
    last_exception: Exception | None = None
    for attempt in range(retries):
        try:
            async with create_async_http_client(timeout=timeout) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    json=json,
                    data=data,
                )
                response.raise_for_status()
                return response
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            last_exception = exc
            if attempt == retries - 1:
                raise
            await asyncio.sleep(retry_interval)
    if last_exception is not None:
        raise last_exception
    raise RuntimeError("Request failed without exception details.")
