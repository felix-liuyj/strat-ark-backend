"""通知渠道发送集成 stub（多渠道：Email / Webhook / Telegram / Lark / Slack / Discord / SMS / AppPush）。

返回拟真 mock 数据；函数签名按真实渠道集成预留：真实实现时这里会按渠道类型分别调用
SMTP、HTTP Webhook、Telegram Bot API、飞书 / Slack / Discord 群机器人、短信网关、推送服务。
当前阶段不发起任何真实发送，仅校验配置完整性后返回拟真结果。
ViewModel 只调用 ``send_test`` / ``dispatch``，绝不在业务层写死渠道协议细节。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

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


def _validate_config(channel_type: str, config: dict[str, object]) -> str | None:
    """校验渠道配置完整性，返回缺失字段提示；完整则返回 None。"""
    required = _REQUIRED_CONFIG_FIELDS.get(channel_type, ())
    missing = [field for field in required if not str(config.get(field, "")).strip()]
    if missing:
        return f"渠道配置不完整，缺少字段：{', '.join(missing)}"
    return None


def send_test(channel_type: str, config: dict[str, object]) -> ChannelSendResult:
    """发送测试通知（mock）。真实实现：按渠道类型走对应发送协议并计时。"""
    error = _validate_config(channel_type, config)
    if error is not None:
        return ChannelSendResult(
            ok=False,
            channel_type=channel_type,
            message=error,
            latency_ms=0,
            sent_at=datetime.now(UTC),
        )
    return ChannelSendResult(
        ok=True,
        channel_type=channel_type,
        message="测试通知已发送",
        latency_ms=120,
        sent_at=datetime.now(UTC),
    )


def dispatch(channel_type: str, config: dict[str, object], title: str, body: str) -> ChannelSendResult:
    """正式投递一条通知到指定渠道（mock）。真实实现：渲染模板后按渠道协议发送。"""
    error = _validate_config(channel_type, config)
    if error is not None:
        return ChannelSendResult(
            ok=False,
            channel_type=channel_type,
            message=error,
            latency_ms=0,
            sent_at=datetime.now(UTC),
        )
    return ChannelSendResult(
        ok=True,
        channel_type=channel_type,
        message=f"已投递 · {title}",
        latency_ms=96,
        sent_at=datetime.now(UTC),
    )
