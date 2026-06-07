"""AI 投研 Agent 集成 stub（TradingAgents 编排）。

返回拟真 mock 数据；函数签名按真实多智能体编排预留：真实实现时这里会调用
TradingAgents 流水线产出趋势判断、投研摘要与信号一致性分析。当前阶段不调用任何
真实 LLM、不接入真实行情，仅返回结构化拟真结果。
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = (
    "BotAiSummary",
    "SignalAlignment",
    "generate_bot_summary",
)


@dataclass(slots=True)
class SignalAlignment:
    """策略信号与 AI 判断一致性。"""

    ai_recommendation: str
    ai_confidence: float
    strategy_signal: str
    bot_direction: str
    aligned: bool
    risk_level: str
    suggested_action: str


@dataclass(slots=True)
class BotAiSummary:
    """机器人维度的 AI 投研摘要。"""

    trend: str
    headline: str
    narrative: str
    alignment: SignalAlignment


def generate_bot_summary(bot_name: str, pairs: list[str]) -> BotAiSummary:
    """生成机器人 AI 投研摘要（mock）。

    真实实现：以机器人持仓与交易对为输入跑 TradingAgents 流水线，汇总趋势与建议。
    """
    return BotAiSummary(
        trend="Trend ↑",
        headline="该 Bot 当前持仓与 AI 趋势判断一致，建议维持。",
        narrative=(
            "BTC 维持上升趋势，动量短期走弱。当前 Bot 持仓方向与 AI 判断一致；"
            "若价格跌破 66,500，建议触发止损并暂停新开仓。"
        ),
        alignment=SignalAlignment(
            ai_recommendation="Watch",
            ai_confidence=0.72,
            strategy_signal="Long",
            bot_direction="Long",
            aligned=True,
            risk_level="Medium",
            suggested_action="维持 · 关注 66.5K",
        ),
    )
