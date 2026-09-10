"""Request and response bodies for bid/hold/skip."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.decisions.models import Decision
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


class DecisionWithTender(DecisionRead):
    """A decision plus enough of the notice to render a pipeline row."""

    tender: TenderSummary
