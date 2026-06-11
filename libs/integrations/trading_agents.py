"""TradingAgents 多智能体投研集成。

编排八类 Agent（Market / Technical / Sentiment / Bull / Bear / Trader / Risk /
Portfolio）的研报产出：经 httpx 调用 LLM 网关（provider-neutral：Anthropic Messages /
OpenAI 兼容）产出结构化研报。**无回退机制**：网关未配置或调用失败抛
``GatewayUnavailableError``，由 ViewModel 转为业务错误（禁止访问对应服务，不伪造研报）。
数值价位（入场 / 止损 / 止盈）由真实行情快照派生（LLM 不产出可执行价格，仅叙事与多空研判）。

网关配置单一事实源（resolve_gateway_config）：管理员在引擎管理页配置的 tradingagents
connection_config（gatewayProvider / gatewayEndpoint / gatewayModel / apiKey，落库），
不走 env；调用方（ViewModel）读库后传入。

约定：AI 只产出**辅助决策**结论，绝不直接下单；是否进入实盘由信号状态机 + 风控
规则约束（见 view_models/signals）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import httpx

from libs.integrations import market_data
from libs.logger import logger

__all__ = (
    "AgentOpinion",
    "AgentRoleEnum",
    "BacktestReviewResult",
    "GatewayConfig",
    "GatewayUnavailableError",
    "MarketAnalysisResult",
    "SignalReviewResult",
    "resolve_gateway_config",
    "review_backtest",
    "review_signal",
    "run_market_analysis",
)


class GatewayUnavailableError(RuntimeError):
    """LLM 网关不可用（未配置或调用失败）；message 直接面向用户展示。"""


@dataclass(slots=True)
class GatewayConfig:
    """LLM 网关配置快照（provider / 端点 / 模型 / 密钥）。"""

    provider: str
    url: str | None
    model: str
    api_key: str | None

    @property
    def ready(self) -> bool:
        return bool(self.api_key)


def resolve_gateway_config(connection_config: dict[str, Any] | None = None) -> GatewayConfig:
    """从引擎管理页落库的 connection_config 合成网关配置（单一事实源，不走 env）。

    connection_config 字段（引擎管理页 TradingAgents 连接配置表单）：
    ``gatewayProvider``（Anthropic / OpenAI / Local，大小写不敏感）、``gatewayEndpoint``、
    ``gatewayModel``、``apiKey``。apiKey 未配置即 ``ready=False``，业务函数将拒绝服务；
    端点留空用 provider 官方默认，模型留空用 claude-opus-4-8。
    """
    cc = connection_config or {}
    provider = str(cc.get("gatewayProvider") or "anthropic").strip().lower()
    if provider == "local":
        provider = "openai"  # Local 网关按 OpenAI 兼容协议调用
    return GatewayConfig(
        provider=provider,
        url=str(cc.get("gatewayEndpoint") or "").strip() or None,
        model=str(cc.get("gatewayModel") or "").strip() or "claude-opus-4-8",
        api_key=str(cc.get("apiKey") or "").strip() or None,
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


async def _base_market_analysis(symbol: str, timeframe: str) -> MarketAnalysisResult:
    """从真实行情派生数值骨架，LLM 只覆盖叙事与研判字段。"""
    detail = await market_data.get_ticker_detail(symbol)
    if detail is None:
        raise GatewayUnavailableError("真实行情不可用，无法生成 AI 市场分析")
    ticker, snapshot = detail
    trend_up = snapshot.trend == "Trend Up"
    signal = "long" if snapshot.rating.lower() == "long" else "watch"
    bull_score = 55 if trend_up else 45
    confidence = round(snapshot.confidence / 100, 2)
    return MarketAnalysisResult(
        symbol=symbol,
        timeframe=timeframe,
        market_state="trend_up" if trend_up else "range",
        signal=signal,
        confidence=confidence,
        risk_level="medium" if confidence < 0.7 else "low",
        entry_zone=[snapshot.entry_low, snapshot.entry_high],
        stop_loss=snapshot.stop_loss,
        take_profit=snapshot.take_profit,
        bull_score=bull_score,
        bear_score=100 - bull_score,
        summary=f"AI 网关未返回摘要；最新价格 {ticker.price:g}，24h 涨跌幅 {ticker.change_pct:g}%。",
        agents=[],
        generated_at=datetime.now(UTC),
    )


def _base_review_signal(symbol: str, direction: str, confidence: float, risk_level: str) -> SignalReviewResult:
    """用传入信号构造最小结果骨架，LLM 覆盖复核叙事。"""
    approve = confidence >= 0.6 and risk_level != "high"
    return SignalReviewResult(
        recommendation="approve" if approve else "review",
        confidence=round(min(max(confidence, 0.0), 1.0), 2),
        risk_level=risk_level,
        summary=f"AI 网关未返回复核摘要；原始信号为 {symbol} {direction}。",
        agents=[],
        generated_at=datetime.now(UTC),
    )


def _base_review_backtest(
    strategy_name: str,
    symbol: str,
    total_return: float,
    max_drawdown: float,
    sharpe: float,
) -> BacktestReviewResult:
    """用真实回测指标构造最小结果骨架，LLM 覆盖复盘叙事。"""
    profitable = total_return > 0 and sharpe >= 1.0
    return BacktestReviewResult(
        verdict="可进一步验证" if profitable else "需优化后再评估",
        strength="AI 网关未返回优势归因",
        weakness="AI 网关未返回弱点归因",
        suggestion="AI 网关未返回改进建议",
        summary=(
            f"AI 网关未返回复盘摘要；{strategy_name} 在 {symbol} 上的总收益 "
            f"{total_return:.1f}%，最大回撤 {max_drawdown:.1f}%，夏普 {sharpe:.2f}。"
        ),
        agents=[],
        generated_at=datetime.now(UTC),
    )


# ============================ LLM 网关（provider-neutral，失败抛 GatewayUnavailableError） ============================

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

_GATEWAY_NOT_CONFIGURED = "AI 网关未配置，请管理员在引擎管理页完成 TradingAgents 网关配置"
_GATEWAY_CALL_FAILED = "AI 网关调用失败，请稍后重试或检查网关配置"


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


async def _llm_json(user_prompt: str, gateway: GatewayConfig) -> dict[str, Any] | None:
    """调用 LLM 网关产出结构化 JSON；任一步失败返回 None（调用方转为 GatewayUnavailableError）。"""
    if not gateway.ready:
        return None
    api_key = gateway.api_key
    model = gateway.model
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            if gateway.provider == "anthropic":
                base = (gateway.url or "https://api.anthropic.com").rstrip("/")
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
                base = (gateway.url or "https://api.openai.com").rstrip("/")
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
        logger.warning(f"trading_agents LLM gateway failed: {exc}")
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


def _coerce_agents(raw: Any) -> list[AgentOpinion]:
    """把 LLM 返回的 agents 转为 AgentOpinion（角色校验 + 截断）。"""
    if not isinstance(raw, list):
        return []
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
    return out


async def run_market_analysis(symbol: str, timeframe: str, *, gateway: GatewayConfig) -> MarketAnalysisResult:
    """多智能体市场分析。网关未配置 / 调用失败抛 GatewayUnavailableError，无回退。"""
    if not gateway.ready:
        raise GatewayUnavailableError(_GATEWAY_NOT_CONFIGURED)
    base = await _base_market_analysis(symbol, timeframe)  # 数值价位来自真实行情
    prompt = (
        f"对交易对 {symbol}（周期 {timeframe}）做多智能体市场研判。"
        f"参考数值骨架：入场区间 {base.entry_zone}，止损 {base.stop_loss}，止盈 {base.take_profit}。"
        "输出 JSON，键："
        '{"marketState":"trend_up|range|trend_down","signal":"long|watch|avoid",'
        '"confidence":0~1,"bullScore":0~100,"bearScore":0~100,"summary":"中文总结",'
        '"agents":[{"role":"market|technical|sentiment|bull|bear|trader|risk|portfolio",'
        '"stance":"短语","summary":"中文","points":["要点"]}]}，agents 需覆盖全部八类角色。'
    )
    data = await _llm_json(prompt, gateway)
    if data is None:
        raise GatewayUnavailableError(_GATEWAY_CALL_FAILED)
    bull = _as_int(data.get("bullScore"), base.bull_score, 0, 100)
    state = str(data.get("marketState", "")).strip().lower()
    signal = str(data.get("signal", "")).strip().lower()
    base.market_state = state if state in _MARKET_STATES else base.market_state
    base.signal = signal if signal in _MARKET_SIGNALS else base.signal
    base.confidence = _as_float(data.get("confidence"), base.confidence, 0.0, 1.0)
    base.bull_score = bull
    base.bear_score = _as_int(data.get("bearScore"), 100 - bull, 0, 100)
    base.summary = str(data.get("summary", "")).strip() or base.summary
    base.agents = _coerce_agents(data.get("agents"))
    return base


async def review_signal(
    symbol: str, direction: str, confidence: float, risk_level: str, *, gateway: GatewayConfig
) -> SignalReviewResult:
    """信号复核。网关未配置 / 调用失败抛 GatewayUnavailableError，无回退。"""
    if not gateway.ready:
        raise GatewayUnavailableError(_GATEWAY_NOT_CONFIGURED)
    base = _base_review_signal(symbol, direction, confidence, risk_level)
    prompt = (
        f"对 {symbol} 的 {direction} 信号（置信度 {confidence}，风险 {risk_level}）做多智能体复核。"
        '输出 JSON：{"recommendation":"approve|review","confidence":0~1,'
        '"riskLevel":"low|medium|high","summary":"中文","agents":[{"role":"market|technical|'
        'sentiment|bull|bear|trader|risk|portfolio","stance":"短语","summary":"中文","points":["要点"]}]}。'
        "复核通过不等于自动下单。"
    )
    data = await _llm_json(prompt, gateway)
    if data is None:
        raise GatewayUnavailableError(_GATEWAY_CALL_FAILED)
    rec = str(data.get("recommendation", "")).strip().lower()
    risk = str(data.get("riskLevel", "")).strip().lower()
    base.recommendation = rec if rec in {"approve", "review"} else base.recommendation
    base.confidence = _as_float(data.get("confidence"), base.confidence, 0.0, 1.0)
    base.risk_level = risk if risk in _RISK_LEVELS else base.risk_level
    base.summary = str(data.get("summary", "")).strip() or base.summary
    base.agents = _coerce_agents(data.get("agents"))
    return base


async def review_backtest(
    strategy_name: str,
    symbol: str,
    total_return: float,
    max_drawdown: float,
    sharpe: float,
    *,
    gateway: GatewayConfig,
) -> BacktestReviewResult:
    """回测复盘。网关未配置 / 调用失败抛 GatewayUnavailableError，无回退。"""
    if not gateway.ready:
        raise GatewayUnavailableError(_GATEWAY_NOT_CONFIGURED)
    base = _base_review_backtest(strategy_name, symbol, total_return, max_drawdown, sharpe)
    prompt = (
        f"对策略「{strategy_name}」在 {symbol} 的回测做归因复盘："
        f"总收益 {total_return}%，最大回撤 {max_drawdown}%，夏普 {sharpe}。"
        '输出 JSON：{"verdict":"中文结论","strength":"中文","weakness":"中文",'
        '"suggestion":"中文改进建议","summary":"中文","agents":[{"role":"market|technical|'
        'sentiment|bull|bear|trader|risk|portfolio","stance":"短语","summary":"中文","points":["要点"]}]}。'
    )
    data = await _llm_json(prompt, gateway)
    if data is None:
        raise GatewayUnavailableError(_GATEWAY_CALL_FAILED)
    base.verdict = str(data.get("verdict", "")).strip() or base.verdict
    base.strength = str(data.get("strength", "")).strip() or base.strength
    base.weakness = str(data.get("weakness", "")).strip() or base.weakness
    base.suggestion = str(data.get("suggestion", "")).strip() or base.suggestion
    base.summary = str(data.get("summary", "")).strip() or base.summary
    base.agents = _coerce_agents(data.get("agents"))
    return base
