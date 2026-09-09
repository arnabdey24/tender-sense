"""SMTP transport for outbox rows.

The interface is one message per call. Batching connections is an optimisation
we can add behind the same :class:`Sender` protocol if it ever matters.
"""

from __future__ import annotations

from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Protocol, runtime_checkable

import aiosmtplib

from app.core.config import settings
from app.core.exceptions import ExternalServiceError
from app.core.logging import get_logger
from app.modules.notifications.models import EmailOutbox

logger = get_logger(__name__)


@runtime_checkable
class Sender(Protocol):
    """Anything that can deliver an outbox row. Tests substitute a fake."""

    async def send(self, email: EmailOutbox) -> str | None:
        """Deliver ``email`` and return its Message-ID, if the transport has one."""
        ...


def build_message(email: EmailOutbox) -> EmailMessage:
    """Assemble a multipart/alternative message with text first, HTML second."""
    message = EmailMessage()
    message["From"] = settings.email_from
    message["To"] = formataddr((email.to_name, email.to_email)) if email.to_name else email.to_email
    message["Subject"] = email.subject
    if settings.email_reply_to:
        message["Reply-To"] = settings.email_reply_to

    unsubscribe_url = (email.context or {}).get("unsubscribe_url")
    if unsubscribe_url:
        message["List-Unsubscribe"] = f"<{unsubscribe_url}>"
        message["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"

    # Generated here rather than by the server so the id we store is the id
    # that was actually sent.
    message["Message-ID"] = make_msgid()
    message.set_content(email.text_body)
    message.add_alternative(email.html_body, subtype="html")
    return message


class SmtpSender:
    """Delivers through the configured SMTP relay (Mailpit in development)."""

    async def send(self, email: EmailOutbox) -> str | None:
        message = build_message(email)
        try:
            await aiosmtplib.send(
                message,
                hostname=settings.smtp_host,
                port=settings.smtp_port,
                username=settings.smtp_user or None,
                password=(
                    settings.smtp_password.get_secret_value() if settings.smtp_password else None
                ),
                # Explicit False (rather than None) so aiosmtplib does not
                # auto-negotiate STARTTLS against a relay we know has none.
                start_tls=settings.smtp_starttls,
                use_tls=settings.smtp_ssl,
            )
        except (aiosmtplib.SMTPException, OSError, ValueError) as exc:
            raise ExternalServiceError(
                f"SMTP delivery to {email.to_email} failed: {exc}",
                code="email_send_failed",
            ) from exc
        message_id = message["Message-ID"]
        return str(message_id) if message_id else None


_sender: Sender | None = None


def get_sender() -> Sender:
    """Process-wide sender used by the pump."""
    global _sender
    if _sender is None:
        _sender = SmtpSender()
    return _sender


def set_sender(sender: Sender | None) -> None:
    """Override (or reset with ``None``) the process-wide sender; used by tests."""
    global _sender
    _sender = sender
