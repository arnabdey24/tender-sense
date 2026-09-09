"""Transactional email: render on enqueue, store in the outbox, pump to SMTP."""

from __future__ import annotations

from app.modules.notifications.email.outbox import (
    backoff_delay,
    claim_batch,
    enqueue,
    mark_failed,
    mark_sent,
    requeue,
)
from app.modules.notifications.email.renderer import (
    EmailTemplateError,
    RenderedEmail,
    TemplateRenderer,
    renderer,
)
from app.modules.notifications.email.sender import Sender, SmtpSender, get_sender, set_sender

__all__ = [
    "EmailTemplateError",
    "RenderedEmail",
    "Sender",
    "SmtpSender",
    "TemplateRenderer",
    "backoff_delay",
    "claim_batch",
    "enqueue",
    "get_sender",
    "mark_failed",
    "mark_sent",
    "renderer",
    "requeue",
    "set_sender",
]
