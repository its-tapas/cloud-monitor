"""
Configuration management for cloud-monitor.

All settings are read from environment variables. A .env file is supported
via python-dotenv when available.
"""

import os
from dataclasses import dataclass, field
from typing import List

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


@dataclass
class RedditConfig:
    client_id: str
    client_secret: str
    user_agent: str
    subreddits: List[str]
    post_limit: int = 25
    poll_interval_seconds: int = 300


@dataclass
class GeminiConfig:
    api_key: str
    model: str = "gemini-1.5-flash"
    analysis_temperature: float = 0.2
    draft_temperature: float = 0.7
    max_output_tokens: int = 2048


@dataclass
class NotifierConfig:
    # Email (SMTP) settings
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    email_from: str = ""
    email_to: str = ""
    # Telegram settings
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""


@dataclass
class AppConfig:
    reddit: RedditConfig
    gemini: GeminiConfig
    notifier: NotifierConfig
    log_level: str = "INFO"


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(
            f"Required environment variable '{name}' is not set. "
            "Please copy .env.example to .env and fill in all required values."
        )
    return value


def _optional(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def load_config() -> AppConfig:
    """Load and validate application configuration from environment variables."""
    subreddits_raw = _optional("REDDIT_SUBREDDITS", "aws+gcpcloud+developersIndia")
    subreddits = [s.strip() for s in subreddits_raw.split("+") if s.strip()]

    reddit_cfg = RedditConfig(
        client_id=_required("REDDIT_CLIENT_ID"),
        client_secret=_required("REDDIT_CLIENT_SECRET"),
        user_agent=_optional(
            "REDDIT_USER_AGENT", "cloud-monitor/1.0 (technical assistance bot)"
        ),
        subreddits=subreddits,
        post_limit=int(_optional("REDDIT_POST_LIMIT", "25")),
        poll_interval_seconds=int(_optional("REDDIT_POLL_INTERVAL_SECONDS", "300")),
    )

    gemini_cfg = GeminiConfig(
        api_key=_required("GEMINI_API_KEY"),
        model=_optional("GEMINI_MODEL", "gemini-1.5-flash"),
        analysis_temperature=float(_optional("GEMINI_ANALYSIS_TEMPERATURE", "0.2")),
        draft_temperature=float(_optional("GEMINI_DRAFT_TEMPERATURE", "0.7")),
        max_output_tokens=int(_optional("GEMINI_MAX_OUTPUT_TOKENS", "2048")),
    )

    notifier_cfg = NotifierConfig(
        smtp_host=_optional("SMTP_HOST", ""),
        smtp_port=int(_optional("SMTP_PORT", "587")),
        smtp_user=_optional("SMTP_USER", ""),
        smtp_password=_optional("SMTP_PASSWORD", ""),
        email_from=_optional("EMAIL_FROM", ""),
        email_to=_optional("EMAIL_TO", ""),
        telegram_bot_token=_optional("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=_optional("TELEGRAM_CHAT_ID", ""),
    )

    return AppConfig(
        reddit=reddit_cfg,
        gemini=gemini_cfg,
        notifier=notifier_cfg,
        log_level=_optional("LOG_LEVEL", "INFO"),
    )
