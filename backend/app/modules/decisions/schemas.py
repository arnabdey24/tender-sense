"""Request and response bodies for bid/hold/skip."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.decisions.models import Decision
from app.modules.matching.models import EligibilityStatus, MatchGrade
from app.modules.tenders.schemas import TenderSummary


class DecisionWrite(BaseModel):
    decision: Decision
    note: str | None = Field(default=None, max_length=4000)


class DecisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tender_id: UUID
    decision: Decision
    note: str | None = None
    is_current: bool
    decided_by_id: UUID | None = None
    created_at: datetime


class DecisionVerdict(BaseModel):
    """The grade behind a decision, when there is one.

    Optional on purpose. A decision is recorded against a *tender*, which
    exists whether or not this organization has scored it — an empty profile,
    or a notice decided on before the pipeline reached it, both produce a real
    decision with no match beside it. Making this required would have meant
    dropping exactly those rows from the pipeline, which is how they became
    invisible in the first place.
    """

    model_config = ConfigDict(from_attributes=True)

    similarity: float
    grade: MatchGrade
    eligibility_status: EligibilityStatus


class DecisionWithTender(DecisionRead):
    """A decision plus enough of the notice to render a pipeline row."""

    tender: TenderSummary
    verdict: DecisionVerdict | None = None
