"""Every customer-facing template must render, escape, and stay one-line."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.core.config import settings
from app.modules.notifications.email.renderer import (
    EmailTemplateError,
    TemplateRenderer,
    renderer,
)

VERIFY_URL = "https://app.tendersense.test/verify/tok-123"
RESET_URL = "https://app.tendersense.test/reset/tok-456"
ACCEPT_URL = "https://app.tendersense.test/invites/tok-789"

CONTEXTS: dict[str, dict[str, Any]] = {
    "verify_email": {
        "user_name": "Ayesha Rahman",
        "verify_url": VERIFY_URL,
        "expires_in_hours": 24,
    },
    "reset_password": {
        "user_name": "Ayesha Rahman",
        "reset_url": RESET_URL,
        "expires_in_minutes": 60,
    },
    "password_changed": {
        "user_name": "Ayesha Rahman",
        "changed_at": "9 September 2026 at 14:05 (Asia/Dhaka)",
        "support_email": "support@tendersense.test",
    },
    "invitation": {
        "inviter_name": "Tanvir Ahmed",
        "org_name": "Brac Infrastructure Ltd.",
        "role": "Bid manager",
        "accept_url": ACCEPT_URL,
        "expires_at": "16 September 2026",
        "invitee_has_account": False,
    },
}

#: The link each template must expose in both bodies.
PRIMARY_URLS = {
    "verify_email": VERIFY_URL,
    "reset_password": RESET_URL,
    "invitation": ACCEPT_URL,
}


@pytest.mark.parametrize("template_key", sorted(CONTEXTS))
def test_every_template_renders_with_valid_context(template_key: str) -> None:
    rendered = renderer.render(template_key, CONTEXTS[template_key])

    assert rendered.subject
    assert rendered.html_body.startswith("<!DOCTYPE html>")
    assert rendered.text_body
    # The plain-text part must be readable prose, not stripped markup.
    assert "<" not in rendered.text_body


@pytest.mark.parametrize("template_key", sorted(CONTEXTS))
def test_subject_is_a_single_stripped_line(template_key: str) -> None:
    subject = renderer.render(template_key, CONTEXTS[template_key]).subject

    assert "\n" not in subject
    assert subject == subject.strip()
    assert "  " not in subject


@pytest.mark.parametrize("template_key", sorted(PRIMARY_URLS))
def test_action_url_appears_in_both_bodies(template_key: str) -> None:
    rendered = renderer.render(template_key, CONTEXTS[template_key])
    url = PRIMARY_URLS[template_key]

    assert url in rendered.html_body
    assert url in rendered.text_body


def test_shared_globals_are_injected_without_the_caller_passing_them() -> None:
    rendered = renderer.render("verify_email", CONTEXTS["verify_email"])

    assert settings.project_name in rendered.subject
    assert settings.app_url.rstrip("/") in rendered.html_body


def test_invitation_wording_differs_for_an_existing_account() -> None:
    without = renderer.render("invitation", CONTEXTS["invitation"])
    with_account = renderer.render(
        "invitation", {**CONTEXTS["invitation"], "invitee_has_account": True}
    )

    assert "set your password" in without.text_body
    assert "set your password" not in with_account.text_body
    assert "already have" in with_account.text_body


def test_html_escapes_markup_in_user_supplied_values() -> None:
    rendered = renderer.render(
        "verify_email",
        {**CONTEXTS["verify_email"], "user_name": "<script>alert('x')</script>"},
    )

    assert "<script>" not in rendered.html_body
    assert "&lt;script&gt;" in rendered.html_body
    # Plain text is not markup, so it stays verbatim.
    assert "<script>" in rendered.text_body


def test_missing_variable_raises_email_template_error() -> None:
    context = dict(CONTEXTS["verify_email"])
    del context["verify_url"]

    with pytest.raises(EmailTemplateError) as excinfo:
        renderer.render("verify_email", context)

    assert excinfo.value.code == "email_template_error"
    assert "verify_url" in str(excinfo.value)


def test_missing_template_raises_email_template_error() -> None:
    with pytest.raises(EmailTemplateError) as excinfo:
        renderer.render("no_such_email", {})

    assert excinfo.value.code == "email_template_error"


def test_renderer_can_be_pointed_at_another_directory(tmp_path: Path) -> None:
    directory = tmp_path
    (directory / "hello.subject.txt").write_text("  Hi\n  {{ name }}  \n")
    (directory / "hello.html.j2").write_text("<p>{{ name }}</p>")
    (directory / "hello.txt.j2").write_text("{{ name }}")

    rendered = TemplateRenderer(directory).render("hello", {"name": "Sam"})

    assert rendered.subject == "Hi Sam"
