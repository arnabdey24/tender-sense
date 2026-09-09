"""The outbox pump: the only place that actually talks to SMTP.

Each message commits on its own, so one undeliverable address cannot roll back
the messages that went out alongside it.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.db.session import session_scope
from app.modules.notifications.email.outbox import claim_batch, mark_failed, mark_sent
from app.modules.notifications.email.sender import Sender, get_sender

logger = get_logger(__name__)

#: Rows claimed per run. Small enough that a slow relay cannot hold locks long.
EMAIL_BATCH_SIZE = 50

#: Suggested schedule for worker.py: ``cron(pump_email_outbox, second=PUMP_CRON_SECOND)``
#: — twice a minute keeps signup emails feeling instant.
PUMP_CRON_SECOND: frozenset[int] = frozenset({0, 30})


async def pump_email_outbox(ctx: dict[str, Any]) -> dict[str, int]:
    """Claim due outbox rows, deliver them, and record each outcome.

    ``ctx["email_sender"]`` overrides the transport, which is how tests inject a
    recording fake.

    Returns:
        Counts of ``claimed``, ``sent`` and ``failed`` messages.
    """
    sender: Sender = ctx.get("email_sender") or get_sender()
    sent = 0
    failed = 0

    async with session_scope() as session:
        emails = await claim_batch(session, limit=EMAIL_BATCH_SIZE)
        # Publish the SENDING flip and drop the row locks before the slow part.
        await session.commit()

        for email in emails:
            try:
                message_id = await sender.send(email)
            except Exception as exc:
                await mark_failed(session, email, error=f"{type(exc).__name__}: {exc}")
                await session.commit()
                failed += 1
                logger.warning(
                    "email_send_failed",
                    email_id=str(email.id),
                    template=email.template_key,
                    attempts=email.attempts,
                    status=email.status.value,
                    error=str(exc),
                )
            else:
                await mark_sent(session, email, message_id=message_id)
                await session.commit()
                sent += 1
                logger.info(
                    "email_sent",
                    email_id=str(email.id),
                    template=email.template_key,
                    message_id=message_id,
                )

    result = {"claimed": len(emails), "sent": sent, "failed": failed}
    if emails:
        logger.info("email_pump_finished", **result)
    return result
