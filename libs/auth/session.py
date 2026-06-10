"""Refresh token jti 白名单（Redis）。

实现规范要求的 rotation + 即时吊销：
- 签发 refresh token 时把 jti 写入白名单（TTL 与 token exp 对齐）；
- 刷新时校验 jti 仍在白名单，随即删除旧 jti 并签发新对（旧 token 重放即被拦）；
- 登出删除 jti，refresh token 立即失效（access 短 TTL 自然过期）。
"""

from libs import redis_cache

__all__ = (
    "is_refresh_jti_active",
    "register_refresh_jti",
    "revoke_all_refresh_jtis",
    "revoke_refresh_jti",
)

_KEY_PREFIX = "auth:refresh"


def _key(user_id: str, jti: str) -> str:
    return f"{_KEY_PREFIX}:{user_id}:{jti}"


async def register_refresh_jti(user_id: str, jti: str, ttl_seconds: int) -> None:
    """签发 refresh token 后登记 jti，TTL 与 token 过期时间对齐。"""
    await redis_cache.set(_key(user_id, jti), "1", ex=ttl_seconds)


async def is_refresh_jti_active(user_id: str, jti: str) -> bool:
    """jti 仍在白名单（未被 rotation 消费、未登出、未过期）。"""
    return bool(await redis_cache.exists(_key(user_id, jti)))


async def revoke_refresh_jti(user_id: str, jti: str) -> None:
    """吊销单个 jti（rotation 消费旧 token / 登出当前会话）。幂等。"""
    await redis_cache.delete(_key(user_id, jti))


async def revoke_all_refresh_jtis(user_id: str) -> None:
    """吊销该用户全部 refresh token（登出所有会话 / 风控强制下线）。"""
    keys = [key async for key in redis_cache.scan_iter(match=f"{_KEY_PREFIX}:{user_id}:*")]
    if keys:
        await redis_cache.delete(*keys)
