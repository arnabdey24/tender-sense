"""Whether this deployment can actually deliver an email.

A misconfigured relay is indistinguishable from a working one until somebody
checks an inbox that never filled. Nothing fails: the outbox row is written,
the pump claims it, the transport reports success, and the message goes
nowhere — or into a spam folder, or to a sink somebody left running. The
tester then reports "no email arrived, nothing in spam", which is true and
names none of the causes.

These are the causes, checked once at startup and again whenever an operator
opens the console. They are deliberately *warnings* rather than a refusal to
boot. A short signing key is a security hole and should stop the process; a
wrong ``EMAIL_FROM`` is a functional fault in one feature, and taking the
whole product down over a typo in an address is a worse outcome than running
with a loud, visible complaint. The complaint is the fix — the previous state
was silence.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings

#: Reserved and special-use TLDs. A `From` on one of these is not deliverable:
#: receivers reject it outright or score it as spam, and Gmail rewrites it.
#: `.local` is the default in `.env.example`, which is how it reaches production.
UNROUTABLE_TLDS = (".local", ".localhost", ".invalid", ".test", ".example")

#: Development mail sinks. Reaching one in production means every message is
#: captured and silently discarded, which looks exactly like success.
MAIL_SINK_HOSTS = ("mailpit", "mailhog", "maildev", "localhost", "127.0.0.1", "::1")


@dataclass(frozen=True, slots=True)
class EmailConfigProblem:
    """One reason mail may not arrive, and what to do about it."""

    code: str
    message: str
    #: True when this alone means nothing can be delivered.
    blocking: bool = True

    def as_text(self) -> str:
        return self.message


def _host_of(address: str) -> str:
    """The domain of a `Name <box@domain>` or bare `box@domain` address."""
    candidate = address.strip()
    if "<" in candidate and ">" in candidate:
        candidate = candidate.split("<", 1)[1].split(">", 1)[0]
    _, _, domain = candidate.rpartition("@")
    return domain.strip().lower()


def email_config_problems(settings: Settings) -> list[EmailConfigProblem]:
    """Everything wrong with this deployment's outbound mail configuration.

    Pure and side-effect free, so the startup log, the operations console and
    the test suite all read the same answer from the same function.
    """
    problems: list[EmailConfigProblem] = []
    host = (settings.smtp_host or "").strip().lower()
    from_domain = _host_of(settings.email_from)
    production = settings.is_production

    if not host:
        problems.append(
            EmailConfigProblem(
                code="smtp_host_missing",
                message="SMTP_HOST is empty, so no message can be delivered.",
            )
        )
    elif host in MAIL_SINK_HOSTS and production:
        problems.append(
            EmailConfigProblem(
                code="smtp_host_is_a_sink",
                message=(
                    f"SMTP_HOST is '{settings.smtp_host}', a local mail sink. Every "
                    "message is captured and discarded, and delivery still reports "
                    "success. Point it at the real relay."
                ),
            )
        )

    if from_domain.endswith(UNROUTABLE_TLDS):
        problems.append(
            EmailConfigProblem(
                code="email_from_unroutable",
                message=(
                    f"EMAIL_FROM is on '{from_domain}', a reserved domain that cannot "
                    "receive mail. Receivers reject it or score it as spam. Set it to "
                    "an address the relay is allowed to send as."
                ),
            )
        )
    elif not from_domain:
        problems.append(
            EmailConfigProblem(
                code="email_from_malformed",
                message="EMAIL_FROM has no domain, so the relay has nothing to send as.",
            )
        )

    needs_auth = host.endswith("gmail.com") or host.endswith("googlemail.com")
    if needs_auth and not settings.smtp_user:
        problems.append(
            EmailConfigProblem(
                code="smtp_user_missing",
                message="SMTP_USER is empty, and Gmail will refuse an unauthenticated relay.",
            )
        )
    if needs_auth and not settings.smtp_password:
        problems.append(
            EmailConfigProblem(
                code="smtp_password_missing",
                message=(
                    "SMTP_PASSWORD is empty. Gmail needs a 16-character App Password, "
                    "not the account password."
                ),
            )
        )
    if (
        needs_auth
        and settings.smtp_user
        and from_domain
        and _host_of(settings.smtp_user) != from_domain
    ):
        problems.append(
            EmailConfigProblem(
                code="email_from_not_verified",
                message=(
                    f"EMAIL_FROM is on '{from_domain}' but the relay signs in as "
                    f"'{settings.smtp_user}'. Google rewrites From unless that account "
                    "is verified to send as it, so mail arrives from the wrong address."
                ),
                blocking=False,
            )
        )

    if host and host not in MAIL_SINK_HOSTS and not (settings.smtp_starttls or settings.smtp_ssl):
        problems.append(
            EmailConfigProblem(
                code="smtp_in_the_clear",
                message=(
                    "Neither SMTP_STARTTLS nor SMTP_SSL is on, so the relay password "
                    "would cross the network in the clear."
                ),
            )
        )

    app_host = (settings.app_url or "").strip().lower()
    if production and ("localhost" in app_host or "127.0.0.1" in app_host or not app_host):
        problems.append(
            EmailConfigProblem(
                code="app_url_not_public",
                message=(
                    f"APP_URL is '{settings.app_url or ''}', so every verification, "
                    "reset and invitation link points somewhere the recipient cannot "
                    "reach. The mail arrives and the link is dead."
                ),
            )
        )

    return problems
