"""JWT token utilities."""

from datetime import datetime, timedelta
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
    exp: float = Field(..., description="Expire timestamp")
    iat: float = Field(..., description="Issued at timestamp")


def create_access_token(
    user_id: str,
    user_type: UserTypeEnum,
    *,
    roles: list[str] | None = None,
    openid: str | None = None,
    expire_days: int | None = None,
) -> str:
    now = datetime.now()
    expire = now + timedelta(days=expire_days or get_settings().JWT_EXPIRE_DAYS)
    payload: dict[str, Any] = {
        "user_id": user_id,
        "user_type": user_type,
        "roles": roles or [],
        "openid": openid,
        "exp": expire.timestamp(),
        "iat": now.timestamp(),
    }
    return jwt.encode(payload, get_settings().JWT_SECRET_KEY, algorithm=get_settings().JWT_ALGORITHM)


def create_refresh_token(user_id: str, user_type: UserTypeEnum, *, expire_days: int | None = None) -> str:
    now = datetime.now()
    expire = now + timedelta(days=expire_days or get_settings().JWT_REFRESH_EXPIRE_DAYS)
    payload: dict[str, Any] = {
        "user_id": user_id,
        "user_type": user_type,
        "token_type": "refresh",
        "exp": expire.timestamp(),
        "iat": now.timestamp(),
    }
    return jwt.encode(payload, get_settings().JWT_SECRET_KEY, algorithm=get_settings().JWT_ALGORITHM)


def decode_access_token(token: str) -> JWTPayload | None:
    try:
        payload = jwt.decode(token, get_settings().JWT_SECRET_KEY, algorithms=[get_settings().JWT_ALGORITHM])
        return JWTPayload(**payload)
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def decode_refresh_token(token: str) -> RefreshTokenPayload | None:
    try:
        payload = jwt.decode(token, get_settings().JWT_SECRET_KEY, algorithms=[get_settings().JWT_ALGORITHM])
        if payload.get("token_type") != "refresh":
            return None
        return RefreshTokenPayload(**payload)
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None
