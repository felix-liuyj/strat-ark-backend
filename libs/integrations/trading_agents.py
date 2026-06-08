"""TradingAgents 多智能体投研集成。

编排八类 Agent（Market / Technical / Sentiment / Bull / Bear / Trader / Risk /
Portfolio）的研报产出：配置了 LLM 网关（``AI_GATEWAY_API_KEY``）时，经 httpx 调用
网关（provider-neutral：Anthropic Messages / OpenAI 兼容）产出结构化研报；未配置或
任一步失败时，回退到确定性拟真研报（同输入同输出，保证离线 / 联调可复现）。数值价位
（入场 / 止损 / 止盈）始终由确定性骨架提供，LLM 仅丰富叙事与多空研判。

约定：AI 只产出**辅助决策**结论，绝不直接下单；是否进入实盘由信号状态机 + 风控
规则约束（见 view_models/signals）。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import httpx

from configs import get_settings
from libs.logger import logger

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


def _demo_market_analysis(symbol: str, timeframe: str) -> MarketAnalysisResult:
    """确定性市场分析（回退 / 数值骨架）。

    用确定性种子派生信心 / 多空分值与价位，保证同 symbol+timeframe 稳定可回放；
    LLM 网关可用时其叙事字段会被真实研报覆盖，数值价位仍沿用此处骨架。
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


def _demo_review_signal(symbol: str, direction: str, confidence: float, risk_level: str) -> SignalReviewResult:
    """确定性信号复核（回退）。

    依据传入信号自身的方向与置信度给出确定性建议；LLM 网关可用时叙事字段被覆盖。
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


def _demo_review_backtest(
    strategy_name: str,
    symbol: str,
    total_return: float,
    max_drawdown: float,
    sharpe: float,
) -> BacktestReviewResult:
    """确定性回测复盘归因（回退）。

    依据传入的总收益 / 回撤 / 夏普给出确定性归因与建议；LLM 网关可用时叙事字段被覆盖。
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


# ============================ LLM 网关（provider-neutral，失败回退 demo） ============================

_HTTP_TIMEOUT = 60.0
_MAX_TOKENS = 4096
_SYSTEM_PROMPT = (
    "你是 TradingAgents 多智能体投研框架的协调器，编排八类 Agent（market / technical / "
    "sentiment / bull / bear / trader / risk / portfolio）协作辩论。你只产出辅助决策结论，"
    "绝不建议直接下单。严格只输出一个 JSON 对象，不要任何额外解释或代码围栏。"
)
_MARKET_STATES = {"trend_up", "range", "trend_down"}
_MARKET_SIGNALS = {"long", "watch", "avoid"}
_RISK_LEVELS = {"low", "medium", "high"}


def _gateway_ready() -> bool:
    """是否配置了可用的 LLM 网关密钥（未配置即回退确定性研报）。"""
    return bool(getattr(get_settings(), "AI_GATEWAY_API_KEY", None))


def _extract_json(text: str) -> dict[str, Any] | None:
    """从模型文本中截取首个 JSON 对象（容忍 ``` 代码围栏与前后缀）。"""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


async def _llm_json(user_prompt: str) -> dict[str, Any] | None:
    """调用配置的 LLM 网关产出结构化 JSON；未配置或任一步失败返回 None（调用方回退）。"""
    settings = get_settings()
    api_key = settings.AI_GATEWAY_API_KEY
    if not api_key:
        return None
    provider = (settings.AI_GATEWAY_PROVIDER or "anthropic").strip().lower()
    model = settings.AI_GATEWAY_MODEL
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            if provider == "anthropic":
                base = (settings.AI_GATEWAY_URL or "https://api.anthropic.com").rstrip("/")
                url = base if base.endswith("/v1/messages") else f"{base}/v1/messages"
                resp = await client.post(
                    url,
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": model,
                        "max_tokens": _MAX_TOKENS,
                        "system": _SYSTEM_PROMPT,
                        "messages": [{"role": "user", "content": user_prompt}],
                    },
                )
                resp.raise_for_status()
                blocks = resp.json().get("content", [])
                text = next((b.get("text", "") for b in blocks if b.get("type") == "text"), "")
            else:
                base = (settings.AI_GATEWAY_URL or "https://api.openai.com").rstrip("/")
                url = base if base.endswith("/chat/completions") else f"{base}/v1/chat/completions"
                resp = await client.post(
                    url,
                    headers={"Authorization": f"Bearer {api_key}", "content-type": "application/json"},
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": _SYSTEM_PROMPT},
                            {"role": "user", "content": user_prompt},
                        ],
                        "response_format": {"type": "json_object"},
                    },
                )
                resp.raise_for_status()
                text = resp.json()["choices"][0]["message"]["content"]
        return _extract_json(text)
    except Exception as exc:
        logger.warning(f"trading_agents LLM gateway fallback: {exc}")
        return None


def _as_float(value: Any, default: float, lo: float, hi: float) -> float:
    try:
        return round(min(max(float(value), lo), hi), 2)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int, lo: int, hi: int) -> int:
    try:
        return int(min(max(float(value), lo), hi))
    except (TypeError, ValueError):
        return default


def _coerce_agents(raw: Any, fallback: list[AgentOpinion]) -> list[AgentOpinion]:
    """把 LLM 返回的 agents 转为 AgentOpinion（角色校验 + 截断）；无有效项则回退确定性观点。"""
    if not isinstance(raw, list):
        return fallback
    valid_roles = {r.value: r for r in AgentRoleEnum}
    out: list[AgentOpinion] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        role = valid_roles.get(str(item.get("role", "")).strip().lower())
        summary = str(item.get("summary", "")).strip()
        if role is None or not summary:
            continue
        points = item.get("points", [])
        out.append(
            AgentOpinion(
                role=role,
                name=_AGENT_NAMES[role],
                stance=str(item.get("stance", "")).strip()[:40] or "Neutral",
                summary=summary,
                points=[str(p).strip() for p in points if str(p).strip()][:6] if isinstance(points, list) else [],
            )
        )
    return out or fallback


async def run_market_analysis(symbol: str, timeframe: str) -> MarketAnalysisResult:
    """多智能体市场分析：LLM 网关可用时产出真实研报，否则回退确定性研报。"""
    base = _demo_market_analysis(symbol, timeframe)
    if not _gateway_ready():
        return base
    prompt = (
        f"对交易对 {symbol}（周期 {timeframe}）做多智能体市场研判。"
        f"参考数值骨架：入场区间 {base.entry_zone}，止损 {base.stop_loss}，止盈 {base.take_profit}。"
        "输出 JSON，键："
        '{"marketState":"trend_up|range|trend_down","signal":"long|watch|avoid",'
        '"confidence":0~1,"bullScore":0~100,"bearScore":0~100,"summary":"中文总结",'
        '"agents":[{"role":"market|technical|sentiment|bull|bear|trader|risk|portfolio",'
        '"stance":"短语","summary":"中文","points":["要点"]}]}，agents 需覆盖全部八类角色。'
    )
    data = await _llm_json(prompt)
    if data is None:
        return base
    bull = _as_int(data.get("bullScore"), base.bull_score, 0, 100)
    state = str(data.get("marketState", "")).strip().lower()
    signal = str(data.get("signal", "")).strip().lower()
    base.market_state = state if state in _MARKET_STATES else base.market_state
    base.signal = signal if signal in _MARKET_SIGNALS else base.signal
    base.confidence = _as_float(data.get("confidence"), base.confidence, 0.0, 1.0)
    base.bull_score = bull
    base.bear_score = _as_int(data.get("bearScore"), 100 - bull, 0, 100)
    base.summary = str(data.get("summary", "")).strip() or base.summary
    base.agents = _coerce_agents(data.get("agents"), base.agents)
    return base


async def review_signal(symbol: str, direction: str, confidence: float, risk_level: str) -> SignalReviewResult:
    """信号复核：LLM 网关可用时产出真实复核，否则回退确定性结论。"""
    base = _demo_review_signal(symbol, direction, confidence, risk_level)
    if not _gateway_ready():
        return base
    prompt = (
        f"对 {symbol} 的 {direction} 信号（置信度 {confidence}，风险 {risk_level}）做多智能体复核。"
        '输出 JSON：{"recommendation":"approve|review","confidence":0~1,'
        '"riskLevel":"low|medium|high","summary":"中文","agents":[{"role":"market|technical|'
        'sentiment|bull|bear|trader|risk|portfolio","stance":"短语","summary":"中文","points":["要点"]}]}。'
        "复核通过不等于自动下单。"
    )
    data = await _llm_json(prompt)
    if data is None:
        return base
    rec = str(data.get("recommendation", "")).strip().lower()
    risk = str(data.get("riskLevel", "")).strip().lower()
    base.recommendation = rec if rec in {"approve", "review"} else base.recommendation
    base.confidence = _as_float(data.get("confidence"), base.confidence, 0.0, 1.0)
    base.risk_level = risk if risk in _RISK_LEVELS else base.risk_level
    base.summary = str(data.get("summary", "")).strip() or base.summary
    base.agents = _coerce_agents(data.get("agents"), base.agents)
    return base


async def review_backtest(
    strategy_name: str,
    symbol: str,
    total_return: float,
    max_drawdown: float,
    sharpe: float,
) -> BacktestReviewResult:
    """回测复盘：LLM 网关可用时产出真实归因，否则回退确定性结论。"""
    base = _demo_review_backtest(strategy_name, symbol, total_return, max_drawdown, sharpe)
    if not _gateway_ready():
        return base
    prompt = (
        f"对策略「{strategy_name}」在 {symbol} 的回测做归因复盘："
        f"总收益 {total_return}%，最大回撤 {max_drawdown}%，夏普 {sharpe}。"
        '输出 JSON：{"verdict":"中文结论","strength":"中文","weakness":"中文",'
        '"suggestion":"中文改进建议","summary":"中文","agents":[{"role":"market|technical|'
        'sentiment|bull|bear|trader|risk|portfolio","stance":"短语","summary":"中文","points":["要点"]}]}。'
    )
    data = await _llm_json(prompt)
    if data is None:
        return base
    base.verdict = str(data.get("verdict", "")).strip() or base.verdict
    base.strength = str(data.get("strength", "")).strip() or base.strength
    base.weakness = str(data.get("weakness", "")).strip() or base.weakness
    base.suggestion = str(data.get("suggestion", "")).strip() or base.suggestion
    base.summary = str(data.get("summary", "")).strip() or base.summary
    base.agents = _coerce_agents(data.get("agents"), base.agents)
    return base
