"""设置页外部连通性工具。"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

import httpx

__all__ = (
    "LlmGatewayResult",
    "test_llm_gateway",
)


@dataclass(slots=True)
class LlmGatewayResult:
    """LLM 模型网关连接测试结果。"""

    ok: bool
    latency_ms: int
    message: str


def _gateway_url(endpoint: str, suffix: str) -> str:
    base = endpoint.strip().rstrip("/")
    return base if base.endswith(suffix) else f"{base}{suffix}"


def _anthropic_request(endpoint: str, model: str, api_key: str) -> tuple[str, dict[str, str], dict[str, object]]:
    return (
        _gateway_url(endpoint or "https://api.anthropic.com", "/v1/messages"),
        {"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        {"model": model, "max_tokens": 1, "messages": [{"role": "user", "content": "ping"}]},
    )


def _openai_request(endpoint: str, model: str, api_key: str) -> tuple[str, dict[str, str], dict[str, object]]:
    return (
        _gateway_url(endpoint or "https://api.openai.com", "/v1/chat/completions"),
        {"Authorization": f"Bearer {api_key}", "content-type": "application/json"},
        {"model": model, "max_tokens": 1, "messages": [{"role": "user", "content": "ping"}]},
    )


def test_llm_gateway(provider: str, model: str, endpoint: str, api_key: str) -> LlmGatewayResult:
    """用真实 HTTP 请求测试 LLM 模型网关连通性。"""
    provider_key = provider.strip().lower()
    builder = _anthropic_request if "anthropic" in provider_key or "claude" in model.lower() else _openai_request
    url, headers, payload = builder(endpoint, model.strip(), api_key.strip())
    started = perf_counter()
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
    except (httpx.HTTPError, ValueError) as exc:
        return LlmGatewayResult(ok=False, latency_ms=round((perf_counter() - started) * 1000), message=str(exc))
    return LlmGatewayResult(ok=True, latency_ms=round((perf_counter() - started) * 1000), message="模型网关连接正常")
