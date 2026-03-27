"""
Tests for src/notifier.py
"""

import pytest
import smtplib
from unittest.mock import MagicMock, patch, call

from src.config import NotifierConfig
from src.draft_generator import DraftResponse
from src.notifier import EmailNotifier, TelegramNotifier, Notifier, NotificationError


@pytest.fixture
def sample_draft():
    return DraftResponse(
        post_id="p1",
        post_title="IAM role not working for Lambda",
        post_url="https://reddit.com/r/aws/p1",
        analysis_summary="IAM trust policy misconfiguration.",
        technical_tags=["IAM", "Lambda"],
        complexity_score=8,
        draft_text="Here is the technical answer to your IAM issue...",
    )


# ---------------------------------------------------------------------------
# EmailNotifier tests
# ---------------------------------------------------------------------------


def _email_config(**kwargs):
    defaults = dict(
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="user@example.com",
        smtp_password="secret",
        email_from="from@example.com",
        email_to="to@example.com",
    )
    defaults.update(kwargs)
    return NotifierConfig(**defaults)


def test_email_notifier_sends_when_configured(sample_draft):
    config = _email_config()
    notifier = EmailNotifier(config)

    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__ = lambda s: mock_smtp
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        result = notifier.send("Test subject", "Test body")

    assert result is True
    mock_smtp.login.assert_called_once_with("user@example.com", "secret")
    mock_smtp.sendmail.assert_called_once()


def test_email_notifier_skips_when_not_configured(sample_draft):
    config = NotifierConfig()  # no SMTP settings
    notifier = EmailNotifier(config)
    result = notifier.send("subject", "body")
    assert result is False


def test_email_notifier_returns_false_on_smtp_error():
    config = _email_config()
    notifier = EmailNotifier(config)

    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_smtp_cls.side_effect = smtplib.SMTPException("Connection refused")
        result = notifier.send("subject", "body")

    assert result is False


def test_email_notifier_returns_false_on_network_error():
    config = _email_config()
    notifier = EmailNotifier(config)

    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_smtp_cls.side_effect = OSError("Network unreachable")
        result = notifier.send("subject", "body")

    assert result is False


# ---------------------------------------------------------------------------
# TelegramNotifier tests
# ---------------------------------------------------------------------------


def _telegram_config(**kwargs):
    defaults = dict(
        telegram_bot_token="123:TOKEN",
        telegram_chat_id="987654",
    )
    defaults.update(kwargs)
    return NotifierConfig(**defaults)


def test_telegram_notifier_sends_when_configured():
    config = _telegram_config()
    notifier = TelegramNotifier(config)

    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.__enter__ = lambda s: mock_response
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response):
        result = notifier.send("Hello Telegram!")

    assert result is True


def test_telegram_notifier_skips_when_not_configured():
    config = NotifierConfig()  # no Telegram settings
    notifier = TelegramNotifier(config)
    result = notifier.send("message")
    assert result is False


def test_telegram_notifier_splits_long_messages():
    config = _telegram_config()
    notifier = TelegramNotifier(config)

    long_text = "X" * 5000  # > MAX_MESSAGE_LENGTH (4096)

    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.__enter__ = lambda s: mock_response
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
        result = notifier.send(long_text)

    assert result is True
    # Should have been called twice (5000 / 4096 = 2 chunks)
    assert mock_urlopen.call_count == 2


def test_telegram_notifier_returns_false_on_url_error():
    import urllib.error

    config = _telegram_config()
    notifier = TelegramNotifier(config)

    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.URLError("Connection refused"),
    ):
        result = notifier.send("message")

    assert result is False


# ---------------------------------------------------------------------------
# Notifier (orchestrator) tests
# ---------------------------------------------------------------------------


def test_notifier_raises_when_no_channel_configured(sample_draft):
    config = NotifierConfig()  # nothing configured
    notifier = Notifier(config)
    with pytest.raises(NotificationError, match="No notification channel"):
        notifier.send_high_value_alert(sample_draft)


def test_notifier_sends_via_email_when_only_email_configured(sample_draft):
    config = _email_config()
    notifier = Notifier(config)

    with patch.object(notifier.email, "send", return_value=True) as mock_email:
        with patch.object(notifier.telegram, "send", return_value=False):
            notifier.send_high_value_alert(sample_draft)

    mock_email.assert_called_once()
    subject, body = mock_email.call_args[0]
    assert "IAM role not working" in subject
    assert "HIGH-VALUE" in body


def test_notifier_sends_via_telegram_when_only_telegram_configured(sample_draft):
    config = _telegram_config()
    notifier = Notifier(config)

    with patch.object(notifier.telegram, "send", return_value=True) as mock_telegram:
        with patch.object(notifier.email, "send", return_value=False):
            notifier.send_high_value_alert(sample_draft)

    mock_telegram.assert_called_once()


def test_notifier_uses_both_channels_when_both_configured(sample_draft):
    # Merge both configs
    config = NotifierConfig(
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="user@example.com",
        smtp_password="secret",
        email_from="from@example.com",
        email_to="to@example.com",
        telegram_bot_token="123:TOKEN",
        telegram_chat_id="987654",
    )
    notifier = Notifier(config)

    with patch.object(notifier.email, "send", return_value=True) as mock_email:
        with patch.object(notifier.telegram, "send", return_value=True) as mock_telegram:
            notifier.send_high_value_alert(sample_draft)

    mock_email.assert_called_once()
    mock_telegram.assert_called_once()
