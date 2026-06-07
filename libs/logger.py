"""Logging utilities."""

import json
import logging
import os
import pathlib

from configs import get_settings

__all__ = (
    "JsonFormatter",
    "api_request_logger",
    "logger",
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        if isinstance(record.msg, dict):
            record.msg = json.dumps(record.msg, ensure_ascii=False)
        return super().format(record)


def init_global_logger() -> logging.Logger:
    app_logger = logging.getLogger(get_settings().APP_NO)
    app_logger.setLevel(logging.INFO)
    if not app_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        app_logger.addHandler(handler)
    return app_logger


def init_api_request_logger() -> logging.Logger:
    request_logger = logging.getLogger(f"{get_settings().APP_NO}.api_requests")
    request_logger.setLevel(logging.INFO)
    if request_logger.handlers:
        return request_logger

    log_dir = pathlib.Path(__file__).resolve().parent.parent / "statics" / "logs"
    os.makedirs(log_dir, exist_ok=True)
    log_file_path = log_dir / "api-requests.log"

    handler = logging.FileHandler(log_file_path, mode="a", encoding="utf-8")
    handler.setFormatter(JsonFormatter("%(message)s"))
    request_logger.addHandler(handler)
    request_logger.propagate = False
    return request_logger


logger = init_global_logger()
api_request_logger = init_api_request_logger()
