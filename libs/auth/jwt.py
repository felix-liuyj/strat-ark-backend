"""JWT token utilities.

access token 短 TTL（分钟级）承载业务请求；refresh token 长 TTL 且携带 jti，
配合 Redis 白名单实现 rotation 与登出即时吊销（见 libs/auth/session.py）。
"""

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from pydantic import BaseModel, Field

from configs import get_settings
from models.account import UserTypeEnum

__all__ = (
    "JWTPayload",
    "RefreshTokenPayload",
    "create_access_token",
    "create_refresh_token",
    "decode_access_token",
    "decode_refresh_token",
)


class JWTPayload(BaseModel):
    user_id: str = Field(..., description="User id")
    user_type: UserTypeEnum = Field(..., description="User type")
    roles: list[str] = Field(default_factory=list, description="Role codes")
    openid: str | None = Field(None, description="Wechat openid")
    exp: float = Field(..., description="Expire timestamp")
    iat: float = Field(..., description="Issued at timestamp")


class RefreshTokenPayload(BaseModel):
    user_id: str = Field(..., description="User id")
    user_type: UserTypeEnum = Field(..., description="User type")
    token_type: str = Field("refresh", description="Token type")
    jti: str = Field(..., description="Token id（Redis 白名单 rotation / 吊销用）")
    exp: float = Field(..., description="Expire timestamp")
    iat: float = Field(..., description="Issued at timestamp")


def create_access_token(
    user_id: str,
    user_type: UserTypeEnum,
    *,
    roles: list[str] | None = None,
    openid: str | None = None,
    expire_minutes: int | None = None,
) -> str:
    now = datetime.now(UTC)
    expire = now + timedelta(minutes=expire_minutes or get_settings().JWT_ACCESS_EXPIRE_MINUTES)
    payload: dict[str, Any] = {
        "user_id": user_id,
        "user_type": user_type,
        "roles": roles or [],
        "openid": openid,
        "exp": expire.timestamp(),
        "iat": now.timestamp(),
    }
    return jwt.encode(payload, get_settings().JWT_SECRET_KEY, algorithm=get_settings().JWT_ALGORITHM)


def create_refresh_token(
    user_id: str, user_type: UserTypeEnum, *, expire_days: int | None = None
) -> tuple[str, str, int]:
    """签发 refresh token，返回 (token, jti, ttl_seconds)；jti 须由调用方写入 Redis 白名单。"""
    now = datetime.now(UTC)
    ttl = timedelta(days=expire_days or get_settings().JWT_REFRESH_EXPIRE_DAYS)
    jti = secrets.token_hex(16)
    payload: dict[str, Any] = {
        "user_id": user_id,
        "user_type": user_type,
        "token_type": "refresh",
        "jti": jti,
        "exp": (now + ttl).timestamp(),
        "iat": now.timestamp(),
    }
    token = jwt.encode(payload, get_settings().JWT_SECRET_KEY, algorithm=get_settings().JWT_ALGORITHM)
    return token, jti, int(ttl.total_seconds())


def decode_access_token(token: str) -> JWTPayload | None:
    try:
        payload = jwt.decode(token, get_settings().JWT_SECRET_KEY, algorithms=[get_settings().JWT_ALGORITHM])
        return JWTPayload(**payload)
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def decode_refresh_token(token: str) -> RefreshTokenPayload | None:
    try:
        payload = jwt.decode(token, get_settings().JWT_SECRET_KEY, algorithms=[get_settings().JWT_ALGORITHM])
        if payload.get("token_type") != "refresh" or not payload.get("jti"):
            return None
        return RefreshTokenPayload(**payload)
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None
