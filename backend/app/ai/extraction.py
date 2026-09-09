"""Reading structured requirements out of a notice.

Extraction never fails the pipeline. A notice whose extraction errors is still
embedded and still matched — it simply carries no attributes, which the rule
engine reads as "unknown" and surfaces as "needs verification" rather than as a
silent rejection.
"""

from __future__ import annotations

import hashlib

from app.ai import get_ai_client
from app.ai.base import AIClient, AIError, Usage
from app.ai.prompts.extraction import SYSTEM_INSTRUCTION, build_prompt
from app.ai.schemas import (
    EXTRACTION_PROMPT_VERSION,
    EXTRACTION_SCHEMA_VERSION,
    TenderAttributes,
)
from app.core.logging import get_logger
from app.modules.tenders.models import Tender

logger = get_logger(__name__)


def extraction_input_hash(tender: Tender) -> str:
    """Digest of the text the model actually sees.

    Recorded on the extraction row so re-running the step over an unchanged
    notice can be skipped without comparing prompts.
    """
    parts = [
        tender.title or "",
        tender.summary or "",
        tender.description or "",
        tender.procuring_entity or "",
        tender.country or "",
        tender.procurement_category.value,
        tender.procurement_method or "",
        EXTRACTION_PROMPT_VERSION,
        str(EXTRACTION_SCHEMA_VERSION),
    ]
    return hashlib.sha256("␟".join(parts).encode()).hexdigest()


def prompt_for(tender: Tender) -> str:
    return build_prompt(
        title=tender.title,
        procuring_entity=tender.procuring_entity,
        country=tender.country,
        category=tender.procurement_category.value,
        method=tender.procurement_method,
        summary=tender.summary,
        description=tender.description,
    )


class ExtractionOutcome:
    """What one extraction attempt produced, successful or not."""

    __slots__ = ("attributes", "error", "input_hash", "usage")

    def __init__(
        self,
        *,
        attributes: TenderAttributes | None,
        usage: Usage,
        input_hash: str,
        error: str | None = None,
    ) -> None:
        self.attributes = attributes
        self.usage = usage
        self.input_hash = input_hash
        self.error = error

    @property
    def succeeded(self) -> bool:
        return self.attributes is not None


async def extract_attributes(
    tender: Tender, *, client: AIClient | None = None
) -> ExtractionOutcome:
    """Ask the model for one notice's attributes.

    Returns an outcome rather than raising: the caller records the failure on
    the extraction row and carries on with embedding and matching.
    """
    ai = client or get_ai_client()
    input_hash = extraction_input_hash(tender)

    try:
        result = await ai.generate_structured(
            prompt=prompt_for(tender),
            schema=TenderAttributes,
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=0.0,
        )
    except AIError as exc:
        logger.warning("extraction_failed", tender_id=str(tender.id), error=str(exc))
        return ExtractionOutcome(
            attributes=None,
            usage=Usage(model=ai.generation_model),
            input_hash=input_hash,
            error=str(exc),
        )

    logger.info(
        "extraction_succeeded",
        tender_id=str(tender.id),
        model=result.usage.model,
        sectors=[s.value for s in result.parsed.sectors],
    )
    return ExtractionOutcome(attributes=result.parsed, usage=result.usage, input_hash=input_hash)
