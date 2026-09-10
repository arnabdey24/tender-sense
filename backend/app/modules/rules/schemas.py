"""The rule definition contract.

These models are the stored shape of a rule set *and* the JSON Schema the
frontend validates against, published at ``/rules/schema``. One definition, so
the builder cannot produce something the engine rejects.

A stored definition is immutable: editing a rule set writes a new version rather
than mutating the old one, because every match records which version graded it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.rules.catalogue import (
    Attribute,
    AttributeType,
    OnMissing,
    Operator,
    Severity,
    get_attribute,
)

#: Bump when the definition shape changes incompatibly. Stored on every version.
RULE_SCHEMA_VERSION = 1


class ProfileValue(BaseModel):
    """Compare against something in our own profile.

    Kept as a reference rather than a copied number so a rule stays true after
    the profile changes: "turnover we can show" should follow the profile, not
    freeze whatever it was the day the rule was written.
    """

    source: Literal["profile"] = "profile"
    field: str


class LiteralValue(BaseModel):
    """Compare against a value typed into the rule."""

    source: Literal["literal"] = "literal"
    data: Any = None


RuleValue = Annotated[ProfileValue | LiteralValue, Field(discriminator="source")]


class Money(BaseModel):
    amount: float
    currency: str = "USD"


class RuleDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    attribute: str
    operator: Operator
    value: RuleValue
    severity: Severity = Severity.HARD
    on_missing: OnMissing = OnMissing.VERIFY
    enabled: bool = True
    label: str = Field(default="", max_length=200)
    #: Preset this came from, if any. Purely informational.
    template: str | None = None

    @model_validator(mode="after")
    def _operator_suits_the_attribute(self) -> RuleDefinition:
        attribute = get_attribute(self.attribute)
        if attribute is None:
            raise ValueError(f"Unknown attribute {self.attribute!r}")
        if self.operator not in attribute.allowed_operators:
            allowed = ", ".join(op.value for op in attribute.allowed_operators)
            raise ValueError(
                f"{self.attribute!r} does not support {self.operator.value!r}. Allowed: {allowed}."
            )
        return self

    @property
    def catalogue_entry(self) -> Attribute:
        entry = get_attribute(self.attribute)
        assert entry is not None  # guaranteed by the validator above
        return entry

    def display_label(self) -> str:
        return self.label or self.catalogue_entry.label


class RuleSetDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = RULE_SCHEMA_VERSION
    combinator: Literal["all"] = "all"
    """Only "all" in v1: an eligibility rule that a bidder may ignore because
    another rule passed is not an eligibility rule."""
    rules: list[RuleDefinition] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def _rule_ids_are_unique(self) -> RuleSetDefinition:
        seen = [rule.id for rule in self.rules]
        duplicates = {value for value in seen if seen.count(value) > 1}
        if duplicates:
            raise ValueError(f"Duplicate rule ids: {', '.join(sorted(duplicates))}")
        return self

    @property
    def active_rules(self) -> list[RuleDefinition]:
        return [rule for rule in self.rules if rule.enabled]


# -- evaluation results -----------------------------------------------------


class RuleStatus(BaseModel):
    """The outcome of one rule against one tender."""

    model_config = ConfigDict(from_attributes=True)

    rule_id: str
    label: str
    attribute: str
    operator: Operator
    severity: Severity
    status: Literal["pass", "fail", "unknown", "warn"]
    #: What the tender actually had, rendered for display.
    tender_value: str | None = None
    #: What the rule wanted, rendered for display.
    expected: str | None = None
    #: One sentence a human can act on.
    reason: str = ""
    source: str = ""
    #: Extraction confidence, when the attribute came from the model.
    confidence: float | None = None
    #: The quote from the notice supporting the tender's value.
    evidence: str | None = None


# -- API bodies -------------------------------------------------------------


class CatalogueAttribute(BaseModel):
    key: str
    label: str
    type: AttributeType
    source: str
    description: str
    profile_field: str | None = None
    operators: list[Operator]


class CatalogueOperator(BaseModel):
    key: Operator
    label: str
    #: Shape the `value` field must take for this operator.
    value_shape: Literal["scalar", "list", "range", "boolean", "days"]


class CataloguePreset(BaseModel):
    key: str
    label: str
    description: str
    attribute: str
    operator: Operator
    severity: Severity
    on_missing: OnMissing
    value: dict[str, Any]


class RuleCatalogue(BaseModel):
    """Everything the builder needs to render itself."""

    attributes: list[CatalogueAttribute]
    operators: list[CatalogueOperator]
    presets: list[CataloguePreset]
    severities: list[str]
    on_missing_options: list[str]


class RuleSetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    is_active: bool
    version_number: int
    definition: RuleSetDefinition
    created_at: datetime
    updated_at: datetime


class RuleSetVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    version_number: int
    definition: RuleSetDefinition
    created_at: datetime
    note: str | None = None


class RuleSetWrite(BaseModel):
    name: str = Field(default="Bidding criteria", min_length=1, max_length=200)
    definition: RuleSetDefinition
    note: str | None = Field(default=None, max_length=500)


class RuleValidationError(BaseModel):
    rule_id: str | None = None
    field: str | None = None
    message: str


class RuleValidationResult(BaseModel):
    valid: bool
    errors: list[RuleValidationError] = Field(default_factory=list)


class PreviewCounts(BaseModel):
    evaluated: int = 0
    eligible: int = 0
    needs_verification: int = 0
    ineligible: int = 0


class PreviewSample(BaseModel):
    tender_id: UUID
    title: str
    status: str
    failing_rules: list[str] = Field(default_factory=list)
    unknown_rules: list[str] = Field(default_factory=list)


class RulePreview(BaseModel):
    """What a draft rule set would do to the pool, before saving it."""

    counts: PreviewCounts
    #: Per rule: how many tenders it would pass, fail or leave unknown. This is
    #: what shows a customer that one careless rule is hiding half the pool.
    per_rule: dict[str, PreviewCounts] = Field(default_factory=dict)
    samples: list[PreviewSample] = Field(default_factory=list)


class RuleTestResult(BaseModel):
    """A draft rule set evaluated against one named tender."""

    tender_id: UUID
    title: str
    eligibility_status: str
    results: list[RuleStatus]
