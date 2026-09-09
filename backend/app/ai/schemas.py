"""Structured shapes the language model is asked to fill in.

These double as the response schema handed to Gemini and as the validation
boundary for whatever comes back, so a hallucinated field type is a clean
validation error rather than a corrupt row.

Every extracted attribute carries a confidence and an evidence quote. That pair
is what keeps the rule engine honest: a requirement with no supporting quote, or
one the model is unsure about, becomes "needs verification" rather than a silent
rejection of a tender the customer could have won.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

#: Bump when the prompt or this schema changes in a way that should invalidate
#: stored extractions. Recorded on every `tender_extractions` row.
EXTRACTION_SCHEMA_VERSION = 1
EXTRACTION_PROMPT_VERSION = "v1"

#: Below this, an attribute is treated as unknown by the rule engine.
MIN_USABLE_CONFIDENCE = 0.5


class Sector(StrEnum):
    """Coarse sectors, deliberately few so the model picks consistently."""

    IT = "it"
    CONSTRUCTION = "construction"
    HEALTHCARE = "healthcare"
    EDUCATION = "education"
    ENERGY = "energy"
    WATER = "water"
    TRANSPORT = "transport"
    AGRICULTURE = "agriculture"
    TELECOM = "telecom"
    FINANCE = "finance"
    ENVIRONMENT = "environment"
    LOGISTICS = "logistics"
    SECURITY = "security"
    OTHER = "other"


class Money(BaseModel):
    amount: float | None = None
    currency: str | None = Field(default=None, description="ISO 4217, e.g. BDT, USD")


class FieldEvidence(BaseModel):
    """Why one extracted attribute should be believed.

    Confidence and quote travel with the attribute so the rule engine can
    refuse to act on a requirement the model was unsure about, and so a user
    can check any claim against the notice itself.
    """

    field: str = Field(description="Name of the attribute this refers to.")
    confidence: float = Field(description="0 = guessed, 1 = stated outright.")
    quote: str | None = Field(default=None, description="Short quote copied from the notice.")


class TenderAttributes(BaseModel):
    """What the model reads out of one notice.

    Nothing here is trusted over portal metadata: the pipeline overwrites
    deadline, method and buyer with the portal's own values, because a scraped
    field is a fact and an inferred one is a guess.
    """

    sectors: list[Sector] = Field(
        default_factory=list, description="Sectors this work belongs to; at most three."
    )
    scope_summary: str | None = Field(
        default=None, description="Two or three sentences describing the work itself."
    )
    key_deliverables: list[str] = Field(
        default_factory=list, description="Concrete things the supplier must deliver."
    )
    required_qualifications_text: str | None = Field(
        default=None, description="Verbatim-ish summary of the eligibility section."
    )

    estimated_value: Money | None = None
    min_annual_turnover: Money | None = Field(
        default=None, description="Minimum annual turnover the bidder must show."
    )
    bid_security: Money | None = Field(
        default=None, description="Bid security / earnest money deposit required."
    )

    required_certifications: list[str] = Field(
        default_factory=list,
        description="Certifications named as mandatory, e.g. ISO 9001, CMMI-3.",
    )
    eligible_countries: list[str] = Field(
        default_factory=list,
        description="ISO 3166-1 alpha-2 codes of countries whose firms may bid. "
        "Empty when the notice does not restrict.",
    )
    min_years_experience: int | None = Field(
        default=None, ge=0, le=100, description="Minimum years of relevant experience."
    )
    similar_projects_required: int | None = Field(
        default=None, ge=0, le=100, description="Count of comparable past contracts required."
    )
    jv_allowed: bool | None = Field(
        default=None, description="Whether a joint venture or consortium may bid."
    )
    local_registration_required: bool | None = Field(
        default=None, description="Whether local registration or incorporation is mandatory."
    )

    #: A list rather than the more natural `dict[str, float]` map, because
    #: pydantic renders an open-ended dict as `additionalProperties`, and the
    #: Gemini Developer API rejects that outright ("only supported in Gemini
    #: Enterprise Agent Platform mode"). The map is rebuilt after parsing.
    field_evidence: list[FieldEvidence] = Field(
        default_factory=list,
        description=(
            "One entry per field you reported above, naming the field, how "
            "confident you are, and the quote that supports it. Omit fields "
            "the notice does not state."
        ),
    )

    def confidence_map(self) -> dict[str, float]:
        """`{field: confidence}`, the shape the rest of the pipeline wants."""
        return {entry.field: entry.confidence for entry in self.field_evidence}

    def evidence_map(self) -> dict[str, str]:
        """`{field: quote}` for every field that came with supporting text."""
        return {entry.field: entry.quote for entry in self.field_evidence if entry.quote}

    def confidence_for(self, field: str) -> float:
        """Confidence for one attribute, defaulting to 'unknown'."""
        for entry in self.field_evidence:
            if entry.field == field:
                return entry.confidence
        return 0.0

    def is_reliable(self, field: str) -> bool:
        """Whether the rule engine may act on this attribute."""
        return self.confidence_for(field) >= MIN_USABLE_CONFIDENCE


class MatchExplanation(BaseModel):
    """The narrative shown on a match, when the model writes one."""

    summary: str = Field(description="One or two sentences on why this fits, or does not.")
    why_matched: list[str] = Field(
        default_factory=list, description="Concrete overlaps with the company's profile."
    )
    gaps: list[str] = Field(
        default_factory=list, description="Requirements the company does not clearly meet."
    )
    risks: list[str] = Field(
        default_factory=list, description="Things worth checking before committing."
    )
    next_step: str | None = Field(default=None, description="The single most useful next action.")
