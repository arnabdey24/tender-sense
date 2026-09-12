"""Endpoints that help someone fill in a form.

Both are authenticated but deliberately **not** organization-scoped. The
research call happens on the onboarding screen, where the person has an
account and no organization yet — that is the whole point of it — so requiring
an org context would put the feature behind the form it exists to fill in.

That makes the user the unit of rate limiting rather than the organization,
which is the opposite of the rest of the application. It is the right choice
here for the same reason: with no org to charge the work to, the only durable
identity is the person.

Neither endpoint writes anything. They return a draft; the form shows it, the
user edits it, and an ordinary save does the rest.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.ai import get_ai_client
from app.ai.base import AIError
from app.ai.research import research_company
from app.ai.writing import improve
from app.core.deps import CurrentUser
from app.core.exceptions import ExternalServiceError
from app.core.logging import get_logger
from app.core.rate_limit import enforce_rate_limit
from app.modules.aiassist.schemas import (
    ResearchRequest,
    ResearchResponse,
    WritingRequest,
    WritingResponse,
)

logger = get_logger(__name__)
router = APIRouter(tags=["ai-assist"])


@router.post(
    "/ai/research-company",
    response_model=ResearchResponse,
    summary="Draft a profile from a company website",
)
async def research(data: ResearchRequest, user: CurrentUser) -> ResearchResponse:
    """Read a company's website and draft its profile for the user to correct.

    The provider fetches the page, not this process — a server-side fetcher
    aimed at a user-supplied address is a request-forgery hole pointed at our
    own network, and the feature does not need one.

    Ten an hour. A person setting up types one address, maybe three while they
    find the right one; a hundred is somebody using our key to read the web.
    """
    await enforce_rate_limit(
        f"research:user:{user.id}",
        limit=10,
        window_seconds=3600,
        message="That is a lot of lookups. Try again in a little while.",
    )

    try:
        result = await research_company(get_ai_client(), url=data.url)
    except AIError as exc:
        logger.info("company_research_failed", url=data.url, error=str(exc))
        raise ExternalServiceError(
            "We could not read that website. Check the address, or fill the "
            "form in yourself — you can always edit it later.",
            code="research_failed",
        ) from exc

    logger.info(
        "company_research_ok",
        user_id=str(user.id),
        retrieved=result.retrieved_url,
        model=result.model,
    )
    return ResearchResponse(
        draft=result.draft, retrieved_url=result.retrieved_url, model=result.model
    )


@router.post(
    "/ai/improve-text",
    response_model=WritingResponse,
    summary="Rewrite one profile field",
)
async def improve_text(data: WritingRequest, user: CurrentUser) -> WritingResponse:
    """Tighten a sentence the user wrote, keeping every fact in it."""
    await enforce_rate_limit(
        f"improve:user:{user.id}",
        limit=60,
        window_seconds=3600,
        message="That is a lot of rewrites. Give it a minute.",
    )

    try:
        suggestion = await improve(get_ai_client(), field=data.field, text=data.text)
    except AIError as exc:
        logger.info("improve_text_failed", field=data.field.value, error=str(exc))
        raise ExternalServiceError(
            "We could not improve that just now. Your text is unchanged.",
            code="improve_failed",
        ) from exc

    return WritingResponse(text=suggestion.text, note=suggestion.note)
