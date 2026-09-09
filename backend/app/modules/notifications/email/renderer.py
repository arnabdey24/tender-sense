"""Jinja2 rendering for transactional email.

Templates live next to this module in ``templates/``. Each logical email is a
key with three files: ``<key>.subject.txt``, ``<key>.html.j2`` and
``<key>.txt.j2``. Undefined variables are an error rather than an empty string
so a missing context key fails at enqueue time instead of shipping a broken
message to a customer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import (
    Environment,
    FileSystemLoader,
    StrictUndefined,
    TemplateError,
    TemplateNotFound,
    UndefinedError,
    select_autoescape,
)
from pydantic import BaseModel, ConfigDict

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.time import utcnow

TEMPLATE_DIR = Path(__file__).parent / "templates"

SUBJECT_SUFFIX = ".subject.txt"
HTML_SUFFIX = ".html.j2"
TEXT_SUFFIX = ".txt.j2"


class EmailTemplateError(AppError):
    """A template is missing, malformed, or a required variable was not given."""

    status_code = 500
    code = "email_template_error"
    message = "Email template could not be rendered."


class RenderedEmail(BaseModel):
    """The three parts of a message, ready to store in the outbox."""

    model_config = ConfigDict(frozen=True)

    subject: str
    html_body: str
    text_body: str


class TemplateRenderer:
    def __init__(self, template_dir: Path | None = None) -> None:
        self.template_dir = template_dir or TEMPLATE_DIR
        self.env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            # Filenames end in ``.j2``; enable escaping for the HTML pair only so
            # that plain-text bodies keep raw ``&`` and quotes.
            autoescape=select_autoescape(
                enabled_extensions=("html.j2", "html", "htm", "xml"),
                default_for_string=False,
                default=False,
            ),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )

    def shared_globals(self) -> dict[str, Any]:
        """Values every template may use without the caller passing them."""
        return {
            "app_name": settings.project_name,
            "app_url": settings.app_url.rstrip("/"),
            "current_year": utcnow().year,
        }

    def render(self, template_key: str, context: dict[str, Any]) -> RenderedEmail:
        """Render ``template_key`` into subject, HTML and plain-text bodies.

        Raises:
            EmailTemplateError: the template is missing or the context is
                incomplete.
        """
        merged = {**self.shared_globals(), **context}
        subject = self._render_one(template_key + SUBJECT_SUFFIX, merged)
        html_body = self._render_one(template_key + HTML_SUFFIX, merged)
        text_body = self._render_one(template_key + TEXT_SUFFIX, merged)
        return RenderedEmail(
            subject=_one_line(subject),
            html_body=html_body.strip() + "\n",
            text_body=text_body.strip() + "\n",
        )

    def _render_one(self, name: str, context: dict[str, Any]) -> str:
        try:
            return self.env.get_template(name).render(context)
        except TemplateNotFound as exc:
            raise EmailTemplateError(f"Email template {exc.name!r} does not exist.") from exc
        except UndefinedError as exc:
            raise EmailTemplateError(f"Email template {name!r} is missing a value: {exc}") from exc
        except TemplateError as exc:
            raise EmailTemplateError(f"Email template {name!r} failed to render: {exc}") from exc


def _one_line(subject: str) -> str:
    """Collapse every whitespace run so the header can never be split."""
    return " ".join(subject.split())


#: Process-wide renderer; the environment caches compiled templates.
renderer = TemplateRenderer()
