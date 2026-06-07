"""Shared helper functions."""

from datetime import UTC, datetime
from pathlib import Path
from secrets import token_urlsafe

from jinja2 import Environment, FileSystemLoader, select_autoescape

from configs import get_settings

__all__ = (
    "build_template_environment",
    "generate_random_token",
    "render_template",
    "utc_now",
)


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def generate_random_token(length: int = 32) -> str:
    return token_urlsafe(length)


def build_template_environment() -> Environment:
    template_dir = Path(get_settings().STATIC_DIR).resolve().parent / "templates"
    return Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(["html", "xml"]),
    )


def render_template(template_name: str, **context: object) -> str:
    environment = build_template_environment()
    template = environment.get_template(template_name)
    return template.render(**context)
