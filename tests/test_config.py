"""
Tests for src/config.py
"""

import os
import pytest
from unittest.mock import patch

from src.config import load_config, _required, _optional, AppConfig


REQUIRED_ENV = {
    "REDDIT_CLIENT_ID": "test_client_id",
    "REDDIT_CLIENT_SECRET": "test_client_secret",
    "GEMINI_API_KEY": "test_gemini_key",
}


def test_load_config_with_required_vars(monkeypatch):
    for key, val in REQUIRED_ENV.items():
        monkeypatch.setenv(key, val)

    config = load_config()

    assert isinstance(config, AppConfig)
    assert config.reddit.client_id == "test_client_id"
    assert config.reddit.client_secret == "test_client_secret"
    assert config.gemini.api_key == "test_gemini_key"


def test_load_config_default_subreddits(monkeypatch):
    for key, val in REQUIRED_ENV.items():
        monkeypatch.setenv(key, val)

    config = load_config()

    assert "aws" in config.reddit.subreddits
    assert "gcpcloud" in config.reddit.subreddits
    assert "developersIndia" in config.reddit.subreddits


def test_load_config_custom_subreddits(monkeypatch):
    for key, val in REQUIRED_ENV.items():
        monkeypatch.setenv(key, val)
    monkeypatch.setenv("REDDIT_SUBREDDITS", "learnpython+dataengineering")

    config = load_config()

    assert config.reddit.subreddits == ["learnpython", "dataengineering"]


def test_load_config_missing_required_raises(monkeypatch):
    monkeypatch.delenv("REDDIT_CLIENT_ID", raising=False)
    monkeypatch.delenv("REDDIT_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(ValueError, match="REDDIT_CLIENT_ID"):
        load_config()


def test_load_config_numeric_overrides(monkeypatch):
    for key, val in REQUIRED_ENV.items():
        monkeypatch.setenv(key, val)
    monkeypatch.setenv("REDDIT_POST_LIMIT", "50")
    monkeypatch.setenv("REDDIT_POLL_INTERVAL_SECONDS", "600")
    monkeypatch.setenv("GEMINI_MAX_OUTPUT_TOKENS", "4096")

    config = load_config()

    assert config.reddit.post_limit == 50
    assert config.reddit.poll_interval_seconds == 600
    assert config.gemini.max_output_tokens == 4096


def test_load_config_notifier_email(monkeypatch):
    for key, val in REQUIRED_ENV.items():
        monkeypatch.setenv(key, val)
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USER", "user@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("EMAIL_FROM", "from@example.com")
    monkeypatch.setenv("EMAIL_TO", "to@example.com")

    config = load_config()

    assert config.notifier.smtp_host == "smtp.example.com"
    assert config.notifier.email_to == "to@example.com"


def test_load_config_notifier_telegram(monkeypatch):
    for key, val in REQUIRED_ENV.items():
        monkeypatch.setenv(key, val)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "99999")

    config = load_config()

    assert config.notifier.telegram_bot_token == "123:abc"
    assert config.notifier.telegram_chat_id == "99999"


def test_required_raises_on_empty(monkeypatch):
    monkeypatch.delenv("SOME_VAR", raising=False)
    with pytest.raises(ValueError, match="SOME_VAR"):
        _required("SOME_VAR")


def test_optional_returns_default(monkeypatch):
    monkeypatch.delenv("MISSING_VAR", raising=False)
    assert _optional("MISSING_VAR", "default_val") == "default_val"


def test_optional_returns_env_value(monkeypatch):
    monkeypatch.setenv("PRESENT_VAR", "hello")
    assert _optional("PRESENT_VAR", "default") == "hello"
