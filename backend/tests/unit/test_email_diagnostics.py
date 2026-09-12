"""Whether a deployment can actually deliver mail.

The bug these exist for is not a crash. Every part of the send path reports
success while the message goes into a sink, or out with a `From` no receiver
will accept, or with a link pointing at a machine the reader does not have.
The tester sees "no email arrived, nothing in spam" and nothing anywhere names
a cause.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.notifications.email.diagnostics import email_config_problems

GOOD: dict[str, object] = {
    "secret_key": "x" * 40,
    "environment": "production",
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 587,
    "smtp_user": "ops@tendersense.io",
    "smtp_password": "abcd efgh ijkl mnop",
    "smtp_starttls": True,
    "email_from": "TenderSense <ops@tendersense.io>",
    "app_url": "https://app.tendersense.io",
}


def problems(**overrides: object) -> set[str]:
    return {p.code for p in email_config_problems(Settings(**{**GOOD, **overrides}))}


def test_a_correctly_configured_deployment_is_quiet() -> None:
    """No false positives: an operator who sees a warning must be able to act."""
    assert problems() == set()


def test_the_shipped_example_configuration_is_caught_in_full() -> None:
    """`.env.example` deployed unchanged, which is how this reaches production.

    All three faults at once, each independently fatal to delivery, and none
    of them producing an error anywhere in the send path.
    """
    found = problems(
        smtp_host="mailpit",
        smtp_port=1025,
        smtp_starttls=False,
        smtp_user="",
        smtp_password=None,
        email_from="TenderSense <no-reply@tendersense.local>",
        app_url="http://localhost:5173",
    )

    assert "smtp_host_is_a_sink" in found
    assert "email_from_unroutable" in found
    assert "app_url_not_public" in found


@pytest.mark.parametrize("tld", [".local", ".localhost", ".invalid", ".test", ".example"])
def test_a_sender_on_a_reserved_domain_is_caught(tld: str) -> None:
    assert "email_from_unroutable" in problems(email_from=f"TenderSense <no-reply@acme{tld}>")


@pytest.mark.parametrize("sink", ["mailpit", "mailhog", "localhost", "127.0.0.1"])
def test_a_development_sink_in_production_is_caught(sink: str) -> None:
    """It swallows everything and reports success, which is worse than an outage."""
    assert "smtp_host_is_a_sink" in problems(smtp_host=sink, smtp_starttls=False)


def test_a_sink_is_fine_outside_production() -> None:
    """Locally it is the point. Complaining would train people to ignore this."""
    assert "smtp_host_is_a_sink" not in problems(
        environment="local", smtp_host="mailpit", smtp_starttls=False
    )


def test_gmail_without_an_app_password_is_caught() -> None:
    assert "smtp_password_missing" in problems(smtp_password=None)


def test_gmail_without_a_user_is_caught() -> None:
    assert "smtp_user_missing" in problems(smtp_user="")


def test_a_sender_the_relay_cannot_send_as_is_flagged_but_not_fatal() -> None:
    """Google rewrites it rather than refusing, so mail arrives — wearing the
    wrong address. Worth saying, not worth calling broken."""
    found = [
        p
        for p in email_config_problems(
            Settings(**{**GOOD, "email_from": "TenderSense <hello@otherdomain.com>"})
        )
        if p.code == "email_from_not_verified"
    ]

    assert found and found[0].blocking is False


def test_credentials_in_the_clear_are_caught() -> None:
    assert "smtp_in_the_clear" in problems(smtp_starttls=False, smtp_ssl=False)


def test_a_link_nobody_can_open_is_caught() -> None:
    """The mail arrives and the link is dead, which reads as a broken product."""
    assert "app_url_not_public" in problems(app_url="http://localhost:5173")


def test_a_missing_relay_is_caught() -> None:
    assert "smtp_host_missing" in problems(smtp_host="")


def test_a_bare_address_is_read_as_well_as_a_display_name() -> None:
    assert "email_from_unroutable" in problems(email_from="no-reply@acme.local")
