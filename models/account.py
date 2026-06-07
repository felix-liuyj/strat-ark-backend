"""Authentication related enums."""

from enum import StrEnum

__all__ = ("PlanEnum", "UserTypeEnum")


class UserTypeEnum(StrEnum):
    ADMIN = "admin"
    STAFF = "staff"
    CLIENT = "client"
    GUEST = "guest"


class PlanEnum(StrEnum):
    """订阅套餐（与前端 Free / Pro / Team 对齐）。"""

    FREE = "free"
    PRO = "pro"
    TEAM = "team"
