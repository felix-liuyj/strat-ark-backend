"""通知渠道发送集成。

Webhook、Telegram、飞书、Slack、Discord 走真实 HTTP 投递；Email / SMS / AppPush
需要独立网关配置，未接入时返回明确失败。
ViewModel 只调用 ``send_test`` / ``dispatch``，绝不在业务层写死渠道协议细节。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter

import httpx

__all__ = (
    "ChannelSendResult",
    "dispatch",
    "send_test",
)


@dataclass(slots=True)
class ChannelSendResult:
    """单次渠道发送结果（test 或正式投递通用）。"""

    ok: bool
    channel_type: str
    message: str
    latency_ms: int
    sent_at: datetime


# 各渠道类型必须具备的关键配置字段（缺失即判为配置不完整）。
_REQUIRED_CONFIG_FIELDS: dict[str, tuple[str, ...]] = {
    "web": (),
    "email": ("inbox",),
    "telegram": ("botToken", "chatId"),
    "lark": ("webhookUrl",),
    "slack": ("webhookUrl",),
    "discord": ("webhookUrl",),
    "webhook": ("url",),
    "sms": ("phone",),
    "apppush": ("deviceToken",),
}

_HTTP_TIMEOUT = 8.0


def _validate_config(channel_type: str, config: dict[str, object]) -> str | None:
    """校验渠道配置完整性，返回缺失字段提示；完整则返回 None。"""
    required = _REQUIRED_CONFIG_FIELDS.get(channel_type, ())
    missing = [field for field in required if not str(config.get(field, "")).strip()]
    if missing:
        return f"渠道配置不完整，缺少字段：{', '.join(missing)}"
    return None


def _result(channel_type: str, ok: bool, message: str, started: float | None = None) -> ChannelSendResult:
    elapsed = int((perf_counter() - started) * 1000) if started is not None else 0
    return ChannelSendResult(
        ok=ok,
        channel_type=channel_type,
        message=message,
        latency_ms=elapsed,
        sent_at=datetime.now(UTC),
    )


def _post(url: str, payload: dict[str, object], headers: dict[str, str] | None = None) -> tuple[bool, str]:
    with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
        response = client.post(url, json=payload, headers=headers)
    if response.is_success:
        return True, "通知已发送"
    return False, f"通知发送失败：HTTP {response.status_code}"


def _send_webhook(config: dict[str, object], title: str, body: str) -> tuple[bool, str]:
    url = str(config.get("url") or config.get("webhookUrl") or "").strip()
    content_type = str(config.get("contentType") or "application/json").strip()
    headers = {"content-type": content_type}
    payload = {"title": title, "body": body, "source": "strat-ark"}
    return _post(url, payload, headers)


def _send_telegram(config: dict[str, object], title: str, body: str) -> tuple[bool, str]:
    token = str(config.get("botToken") or "").strip()
    chat_id = str(config.get("chatId") or "").strip()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    return _post(url, {"chat_id": chat_id, "text": f"{title}\n{body}"})


def _send_chat_webhook(channel_type: str, config: dict[str, object], title: str, body: str) -> tuple[bool, str]:
    url = str(config.get("webhookUrl") or "").strip()
    text = f"{title}\n{body}"
    if channel_type == "lark":
        return _post(url, {"msg_type": "text", "content": {"text": text}})
    if channel_type == "discord":
        return _post(url, {"content": text})
    return _post(url, {"text": text})


def _send(channel_type: str, config: dict[str, object], title: str, body: str) -> tuple[bool, str]:
    if channel_type == "web":
        return True, "站内通知渠道可用"
    if channel_type == "telegram":
        return _send_telegram(config, title, body)
    if channel_type in {"lark", "slack", "discord"}:
        return _send_chat_webhook(channel_type, config, title, body)
    if channel_type == "webhook":
        return _send_webhook(config, title, body)
    return False, f"{channel_type} 发送网关未接入，无法发送真实通知"


def send_test(channel_type: str, config: dict[str, object]) -> ChannelSendResult:
    """发送测试通知。"""
    error = _validate_config(channel_type, config)
    if error is not None:
        return _result(channel_type, False, error)
    started = perf_counter()
    try:
        ok, message = _send(channel_type, config, "StratArk 测试通知", "这是一条渠道连通性测试。")
        return _result(channel_type, ok, message, started)
    except Exception as exc:
        return _result(channel_type, False, f"通知发送失败：{exc}", started)


def dispatch(channel_type: str, config: dict[str, object], title: str, body: str) -> ChannelSendResult:
    """正式投递一条通知到指定渠道。"""
    error = _validate_config(channel_type, config)
    if error is not None:
        return _result(channel_type, False, error)
    started = perf_counter()
    try:
        ok, message = _send(channel_type, config, title, body)
        return _result(channel_type, ok, message, started)
    except Exception as exc:
        return _result(channel_type, False, f"通知发送失败：{exc}", started)
