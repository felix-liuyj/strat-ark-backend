"""Common response models package."""

from responses.common.health import StatusResponseData
from responses.common.oss import PresignPutResponseData

__all__ = (
    "PresignPutResponseData",
    "StatusResponseData",
)
