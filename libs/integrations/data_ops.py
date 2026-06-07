"""数据导出 / 清除服务 stub。

返回拟真 mock 结果；函数签名按真实数据管线（导出打包到对象存储、缓存清理任务）预留。
当前阶段不真正打包或删除任何数据，仅返回操作描述与占位下载地址。
真实实现时这里会触发后台导出任务并写 OSS，或调用缓存层执行清理。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

__all__ = (
    "DataActionResult",
    "LlmGatewayResult",
    "clear_data",
    "export_data",
    "test_llm_gateway",
)


@dataclass(slots=True)
class DataActionResult:
    """数据操作结果。"""

    ok: bool
    message: str
    # 导出场景给出占位下载地址（真实实现为 OSS 预签名 URL）。
    download_url: str | None = None


def export_data(fmt: str = "csv", scope: str = "all") -> DataActionResult:
    """导出交易 / 回测数据（mock）。

    真实实现：后台任务查询数据、序列化为 CSV/JSON 并上传 OSS，返回下载链接。
    """
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return DataActionResult(
        ok=True,
        message="已开始导出 · 数据将打包下载",
        download_url=f"https://example-export.local/strat-ark/{scope}-{stamp}.{fmt}",
    )


def clear_data(target: str) -> DataActionResult:
    """清除数据（行情缓存 / 全部 Bot 与策略，mock）。

    真实实现：调用缓存层或数据层执行删除；危险操作由上游做二次确认。
    """
    label = {"market_cache": "行情缓存", "bots_strategies": "全部 Bot 与策略"}.get(target, target)
    return DataActionResult(ok=True, message=f"已清除{label}")


@dataclass(slots=True)
class LlmGatewayResult:
    """LLM 模型网关连接测试结果。"""

    ok: bool
    latency_ms: int
    message: str


def test_llm_gateway(provider: str, endpoint: str, api_key: str) -> LlmGatewayResult:
    """测试 LLM 模型网关连通性（mock）。

    真实实现：用配置的 endpoint + key 发一次轻量探活请求，记录时延。
    """
    return LlmGatewayResult(ok=True, latency_ms=142, message="模型网关连接正常")
