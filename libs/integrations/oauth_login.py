"""OAuth login code exchange and id_token verification."""

import json
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt

from configs import get_settings

__all__ = ("VerifiedOAuthIdentity", "exchange_oauth_code")

GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}
GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
MICROSOFT_ISS_RE = re.compile(r"^https://login\.microsoftonline\.com/([0-9a-fA-F-]+)/v2\.0$")
JWKS_CACHE_TTL_SECONDS = 3600

_JWKS_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}


@dataclass(frozen=True, slots=True)
class VerifiedOAuthIdentity:
    provider: str
    subject: str
    email: str | None
    email_verified: bool
    name: str | None
    picture: str | None
    raw_claims: dict[str, Any]


async def exchange_oauth_code(
    provider: str,
    code: str,
    redirect_uri: str,
    code_verifier: str,
) -> VerifiedOAuthIdentity:
    if provider == "google":
        return await _exchange_google(code, redirect_uri, code_verifier)
    if provider == "microsoft":
        return await _exchange_microsoft(code, redirect_uri, code_verifier)
    raise ValueError("不支持的第三方登录方式")


def _configured_client_id(provider: str) -> str:
    settings = get_settings()
    value = settings.OAUTH_GOOGLE_CLIENT_ID if provider == "google" else settings.OAUTH_MICROSOFT_CLIENT_ID
    client_id = (value or "").strip()
    if not client_id:
        raise ValueError("该第三方登录尚未配置")
    return client_id


async def _exchange_google(code: str, redirect_uri: str, code_verifier: str) -> VerifiedOAuthIdentity:
    token = await _request_token(
        GOOGLE_TOKEN_URL,
        _token_payload("google", code, redirect_uri, code_verifier),
    )
    claims = await _decode_id_token(token, GOOGLE_JWKS_URL, _configured_client_id("google"))
    _validate_google_claims(claims)
    return _google_identity(claims)


async def _exchange_microsoft(code: str, redirect_uri: str, code_verifier: str) -> VerifiedOAuthIdentity:
    tenant = get_settings().OAUTH_MICROSOFT_TENANT.strip() or "common"
    token_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    jwks_url = f"https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys"
    token = await _request_token(token_url, _token_payload("microsoft", code, redirect_uri, code_verifier))
    claims = await _decode_id_token(token, jwks_url, _configured_client_id("microsoft"))
    _validate_microsoft_claims(claims, tenant)
    return _microsoft_identity(claims)


def _token_payload(provider: str, code: str, redirect_uri: str, code_verifier: str) -> dict[str, str]:
    return {
        "client_id": _configured_client_id(provider),
        "code": code,
        "code_verifier": code_verifier,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }


async def _request_token(url: str, data: dict[str, str]) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=get_settings().OAUTH_TOKEN_TIMEOUT_SECONDS) as client:
            response = await client.post(url, data=data)
        payload = response.json()
    except Exception as exc:
        raise ValueError("第三方登录授权失败，请重新发起登录") from exc
    if response.status_code >= 400:
        raise ValueError(_oauth_error_message(payload))
    return payload


def _oauth_error_message(payload: dict[str, Any]) -> str:
    description = payload.get("error_description") or payload.get("error")
    if isinstance(description, str) and description.strip():
        return "第三方登录授权失败，请重新发起登录"
    return "第三方登录授权失败，请重新发起登录"


async def _decode_id_token(token: dict[str, Any], jwks_url: str, audience: str) -> dict[str, Any]:
    id_token = token.get("id_token")
    if not isinstance(id_token, str) or not id_token:
        raise ValueError("第三方登录未返回身份令牌")
    key = await _public_key_for_token(id_token, jwks_url)
    try:
        claims = jwt.decode(
            id_token,
            key=key,
            algorithms=["RS256"],
            audience=audience,
            options={"require": ["exp", "iat"], "verify_iss": False},
        )
    except jwt.PyJWTError as exc:
        raise ValueError("第三方身份令牌校验失败") from exc
    return dict(claims)


async def _public_key_for_token(id_token: str, jwks_url: str) -> Any:
    try:
        header = jwt.get_unverified_header(id_token)
    except jwt.PyJWTError as exc:
        raise ValueError("第三方身份令牌格式无效") from exc
    kid = header.get("kid")
    for key in await _get_jwks(jwks_url):
        if key.get("kid") == kid:
            return jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key))
    raise ValueError("第三方身份令牌签名无法校验")


async def _get_jwks(url: str) -> list[dict[str, Any]]:
    expires_at, cached = _JWKS_CACHE.get(url, (0.0, []))
    if cached and expires_at > time.time():
        return cached
    try:
        async with httpx.AsyncClient(timeout=get_settings().OAUTH_TOKEN_TIMEOUT_SECONDS) as client:
            payload = (await client.get(url)).json()
    except Exception as exc:
        raise ValueError("第三方身份公钥获取失败") from exc
    keys = payload.get("keys") if isinstance(payload, dict) else None
    if not isinstance(keys, list):
        raise ValueError("第三方身份公钥获取失败")
    _JWKS_CACHE[url] = (time.time() + JWKS_CACHE_TTL_SECONDS, keys)
    return keys


def _validate_google_claims(claims: dict[str, Any]) -> None:
    if claims.get("iss") not in GOOGLE_ISSUERS:
        raise ValueError("第三方身份令牌来源无效")
    if not claims.get("sub"):
        raise ValueError("第三方身份令牌缺少用户标识")


def _validate_microsoft_claims(claims: dict[str, Any], tenant: str) -> None:
    tid = str(claims.get("tid") or "").lower()
    match = MICROSOFT_ISS_RE.match(str(claims.get("iss") or ""))
    if not tid or match is None or match.group(1).lower() != tid:
        raise ValueError("第三方身份令牌来源无效")
    configured = tenant.strip().lower()
    if configured != "common" and tid != configured:
        raise ValueError("第三方身份租户不匹配")


def _google_identity(claims: dict[str, Any]) -> VerifiedOAuthIdentity:
    return VerifiedOAuthIdentity(
        provider="google",
        subject=str(claims["sub"]),
        email=_claim_str(claims, "email"),
        email_verified=_claim_bool(claims, "email_verified"),
        name=_claim_str(claims, "name"),
        picture=_claim_str(claims, "picture"),
        raw_claims=claims,
    )


def _microsoft_identity(claims: dict[str, Any]) -> VerifiedOAuthIdentity:
    email = _claim_str(claims, "email") or _claim_str(claims, "preferred_username") or _claim_str(claims, "upn")
    subject = _claim_str(claims, "oid") or _claim_str(claims, "sub")
    if not subject:
        raise ValueError("第三方身份令牌缺少用户标识")
    return VerifiedOAuthIdentity(
        provider="microsoft",
        subject=subject,
        email=email,
        email_verified=bool(email),
        name=_claim_str(claims, "name"),
        picture=None,
        raw_claims=claims,
    )


def _claim_str(claims: dict[str, Any], key: str) -> str | None:
    value = claims.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _claim_bool(claims: dict[str, Any], key: str) -> bool:
    value = claims.get(key)
    if isinstance(value, bool):
        return value
    return isinstance(value, str) and value.lower() == "true"
