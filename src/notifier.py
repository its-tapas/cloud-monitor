"""
Notification module.

Sends the developer an alert (with the Gemini-generated draft) via:
  - Email (SMTP / TLS)
  - Telegram (Bot API)

At least one channel must be configured. If both are configured, both are used.
"""

import logging
import smtplib
import urllib.error
import urllib.parse
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from .config import NotifierConfig
from .draft_generator import DraftResponse

logger = logging.getLogger(__name__)


class NotificationError(Exception):
    """Raised when no notification channel is available or all channels fail."""


class EmailNotifier:
    """Sends notifications via SMTP with STARTTLS."""

    def __init__(self, config: NotifierConfig):
        self.config = config

    def _is_configured(self) -> bool:
        cfg = self.config
        return all(
            [cfg.smtp_host, cfg.smtp_user, cfg.smtp_password, cfg.email_from, cfg.email_to]
        )

    def send(self, subject: str, body: str) -> bool:
        """
        Send an email.

        Returns ``True`` on success, ``False`` if not configured or on error.
        """
        if not self._is_configured():
            logger.debug("Email notifier not configured – skipping.")
            return False

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.config.email_from
        msg["To"] = self.config.email_to
        msg.attach(MIMEText(body, "plain", "utf-8"))

        try:
            with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port, timeout=30) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.login(self.config.smtp_user, self.config.smtp_password)
                smtp.sendmail(self.config.email_from, self.config.email_to, msg.as_string())
            logger.info("Email notification sent to %s", self.config.email_to)
            return True
        except smtplib.SMTPException as exc:
            logger.error("SMTP error sending notification: %s", exc)
            return False
        except OSError as exc:
            logger.error("Network error sending email notification: %s", exc)
            return False


class TelegramNotifier:
    """Sends notifications via the Telegram Bot API."""

    TELEGRAM_API_BASE = "https://api.telegram.org/bot"
    MAX_MESSAGE_LENGTH = 4096

    def __init__(self, config: NotifierConfig):
        self.config = config

    def _is_configured(self) -> bool:
        return bool(self.config.telegram_bot_token and self.config.telegram_chat_id)

    def _send_chunk(self, text: str) -> bool:
        url = f"{self.TELEGRAM_API_BASE}{self.config.telegram_bot_token}/sendMessage"
        payload = json_encode(
            {
                "chat_id": self.config.telegram_chat_id,
                "text": text,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            }
        )
        req = urllib.request.Request(
            url,
            data=payload.encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status != 200:
                    logger.error("Telegram API returned status %d", resp.status)
                    return False
            return True
        except urllib.error.URLError as exc:
            logger.error("Telegram API error: %s", exc)
            return False

    def send(self, text: str) -> bool:
        """
        Send a Telegram message, splitting at MAX_MESSAGE_LENGTH if needed.

        Returns ``True`` if all chunks were sent successfully.
        """
        if not self._is_configured():
            logger.debug("Telegram notifier not configured – skipping.")
            return False

        # Split long messages into chunks
        chunks = [
            text[i : i + self.MAX_MESSAGE_LENGTH]
            for i in range(0, len(text), self.MAX_MESSAGE_LENGTH)
        ]
        success = True
        for chunk in chunks:
            if not self._send_chunk(chunk):
                success = False
        if success:
            logger.info("Telegram notification sent to chat %s", self.config.telegram_chat_id)
        return success


def json_encode(obj: dict) -> str:
    """Minimal JSON serialiser (avoids importing json at module level)."""
    import json

    return json.dumps(obj, ensure_ascii=False)


class Notifier:
    """
    Orchestrates all notification channels.

    Raises :class:`NotificationError` if no channel is configured.
    """

    def __init__(self, config: NotifierConfig):
        self.email = EmailNotifier(config)
        self.telegram = TelegramNotifier(config)

    def _any_configured(self) -> bool:
        return self.email._is_configured() or self.telegram._is_configured()

    def send_high_value_alert(self, draft: DraftResponse) -> None:
        """
        Send an alert to the developer with the generated draft response.

        Uses all configured channels. Raises :class:`NotificationError` if
        no channel is configured.
        """
        if not self._any_configured():
            raise NotificationError(
                "No notification channel is configured. "
                "Please set SMTP_* or TELEGRAM_* environment variables."
            )

        subject = (
            f"[cloud-monitor] High-Value Post: {draft.post_title[:60]}"
            + ("..." if len(draft.post_title) > 60 else "")
        )
        body = draft.format_for_notification()

        email_ok = self.email.send(subject, body)
        telegram_ok = self.telegram.send(body)

        if not email_ok and not telegram_ok:
            logger.warning(
                "All notification channels failed for post %s.", draft.post_id
            )
        else:
            logger.info("Notification sent for high-value post %s.", draft.post_id)
