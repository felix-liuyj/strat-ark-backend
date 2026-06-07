"""第三方 OAuth 绑定服务 stub。

返回拟真 mock 结果；函数签名按真实 OAuth 授权流程（换取 token、拉取 userinfo、
校验 id_token）预留。当前阶段不发起任何真实授权跳转或网络请求。
真实实现时这里会用 PKCE / authorization code 换 token 并校验身份。
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = (
    "OAuthBindResult",
    "simulate_bind",
)

# 各提供方默认账号标识占位（前端未传 accountLabel 时使用）。
_DEFAULT_LABELS: dict[str, str] = {
    "google": "user@gmail.com",
    "microsoft": "user@outlook.com",
    "github": "@user",
    "apple": "user@privaterelay.appleid.com",
}


@dataclass(slots=True)
class OAuthBindResult:
    """绑定结果。"""

    ok: bool
    provider: str
    account_label: str
    message: str


def simulate_bind(provider: str, account_label: str = "") -> OAuthBindResult:
    """模拟第三方账号绑定（无真实授权）。

    真实实现：完成 OAuth 授权码换 token、校验 id_token、提取标准 claims 后绑定。
    """
    label = account_label.strip() or _DEFAULT_LABELS.get(provider.lower(), provider)
    return OAuthBindResult(
        ok=True,
        provider=provider,
        account_label=label,
        message="绑定成功",
    )
