"""TradingAgents 多智能体投研集成 stub。

返回拟真 mock 数据；函数签名按真实 TradingAgents 多智能体框架预留：真实实现时
这里会编排八类 Agent（Market / Technical / Sentiment / Bull / Bear / Trader /
Risk / Portfolio）协作辩论，并通过 LLM 网关产出结构化研报。当前阶段不调用任何
LLM、不发起真实网络请求，仅返回确定性的拟真结构化结论。

约定：AI 只产出**辅助决策**结论，绝不直接下单；是否进入实盘由信号状态机 + 风控
规则约束（见 view_models/signals）。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

__all__ = (
    "AgentOpinion",
    "AgentRoleEnum",
    "BacktestReviewResult",
    "MarketAnalysisResult",
    "SignalReviewResult",
    "review_backtest",
    "review_signal",
    "run_market_analysis",
)


class AgentRoleEnum(StrEnum):
    """八类 Agent 角色（与前端 AI Research 卡片对齐）。"""

    MARKET = "market"
    TECHNICAL = "technical"
    SENTIMENT = "sentiment"
    BULL = "bull"
    BEAR = "bear"
    TRADER = "trader"
    RISK = "risk"
    PORTFOLIO = "portfolio"


@dataclass(slots=True)
class AgentOpinion:
    """单个 Agent 的观点输出。"""

    role: AgentRoleEnum
    name: str
    stance: str
    summary: str
    points: list[str] = field(default_factory=list)


@dataclass(slots=True)
class MarketAnalysisResult:
    """市场分析研报（结构化输出，对应前端 Structured JSON）。"""

    symbol: str
    timeframe: str
    market_state: str
    signal: str
    confidence: float
    risk_level: str
    entry_zone: list[float]
    stop_loss: float
    take_profit: list[float]
    bull_score: int
    bear_score: int
    summary: str
    agents: list[AgentOpinion]
    generated_at: datetime


@dataclass(slots=True)
class SignalReviewResult:
    """信号复核结论（风控 / 多智能体对信号的二次评估）。"""

    recommendation: str
    confidence: float
    risk_level: str
    summary: str
    agents: list[AgentOpinion]
    generated_at: datetime


@dataclass(slots=True)
class BacktestReviewResult:
    """回测复盘结论（对回测结果的归因与改进建议）。"""

    verdict: str
    strength: str
    weakness: str
    suggestion: str
    summary: str
    agents: list[AgentOpinion]
    generated_at: datetime


# 八类 Agent 的固定展示名（真实实现里由各 Agent 自报）。
_AGENT_NAMES: dict[AgentRoleEnum, str] = {
    AgentRoleEnum.MARKET: "Market Analyst",
    AgentRoleEnum.TECHNICAL: "Technical Analyst",
    AgentRoleEnum.SENTIMENT: "Sentiment Analyst",
    AgentRoleEnum.BULL: "Bull Researcher",
    AgentRoleEnum.BEAR: "Bear Researcher",
    AgentRoleEnum.TRADER: "Trader",
    AgentRoleEnum.RISK: "Risk Manager",
    AgentRoleEnum.PORTFOLIO: "Portfolio Manager",
}


def _deterministic_unit(seed: str) -> float:
    """由字符串种子派生 [0,1) 的确定性浮点，保证同输入同输出（拟真但稳定）。"""
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def _build_market_agents(symbol: str, bull_score: int) -> list[AgentOpinion]:
    """构造八类 Agent 的市场观点（mock 文案，按 bull_score 微调措辞）。"""
    leaning_bull = bull_score >= 50
    trend_word = "上升趋势" if leaning_bull else "区间震荡"
    structure_word = "抬升" if leaning_bull else "受阻"
    return [
        AgentOpinion(
            role=AgentRoleEnum.MARKET,
            name=_AGENT_NAMES[AgentRoleEnum.MARKET],
            stance="Trend Up" if leaning_bull else "Range",
            summary=f"{symbol} 处于{trend_word}，高点结构{structure_word}。",
            points=["市场结构判定", "趋势/震荡分类", "关键价位识别"],
        ),
        AgentOpinion(
            role=AgentRoleEnum.TECHNICAL,
            name=_AGENT_NAMES[AgentRoleEnum.TECHNICAL],
            stance="Neutral",
            summary="EMA 多头排列维持，RSI 自高位回落，MACD 红柱收敛，短期动量走弱。",
            points=["EMA 多头排列", "RSI 高位回落", "MACD 红柱收敛"],
        ),
        AgentOpinion(
            role=AgentRoleEnum.SENTIMENT,
            name=_AGENT_NAMES[AgentRoleEnum.SENTIMENT],
            stance="Mild Bull",
            summary="资金费率正常，社交热度回升但未过热，无重大利空新闻，情绪中性偏多。",
            points=["资金费率正常", "社交热度回升", "无重大利空"],
        ),
        AgentOpinion(
            role=AgentRoleEnum.BULL,
            name=_AGENT_NAMES[AgentRoleEnum.BULL],
            stance="Long",
            summary="趋势结构完好，关键阻力突破有效，现货净流入支撑上行。",
            points=["突破有效", "现货净流入", "回调缩量"],
        ),
        AgentOpinion(
            role=AgentRoleEnum.BEAR,
            name=_AGENT_NAMES[AgentRoleEnum.BEAR],
            stance="Caution",
            summary="顶背离风险与上方套牢盘，量能不足，存在假突破风险。",
            points=["顶背离风险", "上方套牢盘", "量能不足"],
        ),
        AgentOpinion(
            role=AgentRoleEnum.TRADER,
            name=_AGENT_NAMES[AgentRoleEnum.TRADER],
            stance="Wait Pullback",
            summary="建议等待回踩入场区间企稳后分批介入，避免追高。",
            points=["分批入场", "回踩确认", "避免追高"],
        ),
        AgentOpinion(
            role=AgentRoleEnum.RISK,
            name=_AGENT_NAMES[AgentRoleEnum.RISK],
            stance="Medium",
            summary="波动率中性，建议中等仓位，单笔风险不超过账户 5%，硬止损保护。",
            points=["波动率中性", "中等仓位", "单笔风险 ≤ 5%"],
        ),
        AgentOpinion(
            role=AgentRoleEnum.PORTFOLIO,
            name=_AGENT_NAMES[AgentRoleEnum.PORTFOLIO],
            stance="30% Pos",
            summary="综合各 Agent，建议观望并预留约 30% 仓位，等待回踩确认后分批入场。",
            points=["综合各 Agent", "预留 30% 仓位", "分批入场"],
        ),
    ]


def run_market_analysis(symbol: str, timeframe: str) -> MarketAnalysisResult:
    """运行多智能体市场分析（mock，结构化研报）。

    真实实现：编排八类 Agent 协作辩论并经 LLM 网关产出结构化结论；本 stub 用
    确定性种子派生信心/多空分值，保证同 symbol+timeframe 稳定可回放。
    """
    unit = _deterministic_unit(f"{symbol}:{timeframe}:market")
    confidence = round(0.5 + unit * 0.35, 2)
    bull_score = int(45 + unit * 20)
    bear_score = 100 - bull_score
    leaning_bull = bull_score >= 50

    base = round(60000 + unit * 12000, 0)
    entry_low = round(base, 0)
    entry_high = round(base * 1.01, 0)
    return MarketAnalysisResult(
        symbol=symbol,
        timeframe=timeframe,
        market_state="trend_up" if leaning_bull else "range",
        signal="watch" if 0.55 <= confidence < 0.7 else ("long" if leaning_bull else "avoid"),
        confidence=confidence,
        risk_level="medium" if confidence < 0.7 else "low",
        entry_zone=[entry_low, entry_high],
        stop_loss=round(base * 0.975, 0),
        take_profit=[round(base * 1.03, 0), round(base * 1.05, 0)],
        bull_score=bull_score,
        bear_score=bear_score,
        summary=(
            f"{symbol} 维持{'上升趋势' if leaning_bull else '区间震荡'}，"
            "但短期动量走弱、量能未持续放大；情绪面中性偏多，资金费率正常。"
            "建议观望为主，等待回踩入场区间企稳后再考虑分批介入，"
            "若有效跌破止损位则趋势假设失效，建议中等仓位、单笔风险不超过账户 5%。"
        ),
        agents=_build_market_agents(symbol, bull_score),
        generated_at=datetime.now(UTC),
    )


def review_signal(symbol: str, direction: str, confidence: float, risk_level: str) -> SignalReviewResult:
    """对单条信号做多智能体复核（mock）。

    真实实现：Risk / Trader / Portfolio 等 Agent 结合实时行情与持仓约束复核信号；
    本 stub 依据传入信号自身的方向与置信度给出确定性建议。
    """
    approve = confidence >= 0.6 and risk_level != "high"
    return SignalReviewResult(
        recommendation="approve" if approve else "review",
        confidence=round(min(max(confidence, 0.0), 1.0), 2),
        risk_level=risk_level,
        summary=(
            f"{symbol} {direction} 信号与当前市场结构"
            f"{'基本一致，可在风控约束下批准' if approve else '存在分歧，建议人工二次确认'}。"
            "批准不等于自动下单，是否进入实盘仍受 Live Mode 流程与风控规则约束。"
        ),
        agents=[
            AgentOpinion(
                role=AgentRoleEnum.TECHNICAL,
                name=_AGENT_NAMES[AgentRoleEnum.TECHNICAL],
                stance="Confirm" if approve else "Mixed",
                summary="技术结构与信号方向" + ("一致" if approve else "存在背离"),
                points=["方向校验", "关键价位校验"],
            ),
            AgentOpinion(
                role=AgentRoleEnum.RISK,
                name=_AGENT_NAMES[AgentRoleEnum.RISK],
                stance=risk_level.capitalize(),
                summary="风险敞口在可控范围" if approve else "风险偏高，建议降低仓位或人工确认",
                points=["仓位约束", "止损校验"],
            ),
            AgentOpinion(
                role=AgentRoleEnum.PORTFOLIO,
                name=_AGENT_NAMES[AgentRoleEnum.PORTFOLIO],
                stance="Allocate" if approve else "Hold",
                summary="可纳入组合分批执行" if approve else "暂缓纳入，等待更明确信号",
                points=["组合相关性", "敞口占比"],
            ),
        ],
        generated_at=datetime.now(UTC),
    )


def review_backtest(
    strategy_name: str,
    symbol: str,
    total_return: float,
    max_drawdown: float,
    sharpe: float,
) -> BacktestReviewResult:
    """对回测结果做多智能体复盘归因（mock）。

    真实实现：结合权益曲线、回撤分布与交易明细做归因，并经 LLM 网关产出改进建议；
    本 stub 依据传入的总收益 / 回撤 / 夏普给出确定性归因与建议。
    """
    profitable = total_return > 0 and sharpe >= 1.0
    return BacktestReviewResult(
        verdict="可进一步验证" if profitable else "需优化后再评估",
        strength="趋势捕捉强" if profitable else "信号筛选稳健",
        weakness="震荡区间连亏" if abs(max_drawdown) >= 8 else "盈亏比偏低",
        suggestion="加入波动率过滤与冷却机制，在 ADX < 20 时暂停开仓",
        summary=(
            f"{strategy_name} 在 {symbol} 上的收益主要来自趋势行情；"
            f"回撤集中于横盘阶段（最大回撤 {max_drawdown:.1f}%）。"
            "建议加入波动率过滤与冷却机制，预计可降低约 30% 横盘回撤。"
        ),
        agents=[
            AgentOpinion(
                role=AgentRoleEnum.MARKET,
                name=_AGENT_NAMES[AgentRoleEnum.MARKET],
                stance="Trend-driven",
                summary="收益高度依赖趋势行情，横盘阶段表现弱",
                points=["趋势依赖", "横盘回撤"],
            ),
            AgentOpinion(
                role=AgentRoleEnum.RISK,
                name=_AGENT_NAMES[AgentRoleEnum.RISK],
                stance="Medium" if abs(max_drawdown) < 12 else "High",
                summary=f"最大回撤 {max_drawdown:.1f}%，建议加入冷却机制控制连亏",
                points=["回撤控制", "连亏冷却"],
            ),
            AgentOpinion(
                role=AgentRoleEnum.PORTFOLIO,
                name=_AGENT_NAMES[AgentRoleEnum.PORTFOLIO],
                stance="Optimize",
                summary="加波动率过滤后可提升组合稳定性",
                points=["波动率过滤", "组合稳定性"],
            ),
        ],
        generated_at=datetime.now(UTC),
    )
