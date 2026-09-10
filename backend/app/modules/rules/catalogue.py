"""What a rule can be written about.

The catalogue is the contract shared by three things that must not drift apart:
the evaluation engine, the API that tells the frontend what to offer, and the
rule builder UI. Adding an attribute here makes it available everywhere at once;
there is no second list to update.

Each attribute declares where its value comes from, because that determines how
much the engine may trust it:

* ``portal_metadata`` — scraped from the notice. A fact.
* ``ai_extraction`` — read out by the model. A claim, carrying a confidence and
  an evidence quote, and treated as unknown below the confidence floor.
* ``derived`` — computed from the tender row itself.

That distinction is the whole reason eligibility has three outcomes rather than
two: a rule over an extracted attribute the model was unsure about cannot
honestly say "no", only "check this".
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field


class AttributeType(enum.StrEnum):
    MONEY = "money"
    LIST = "list"
    ENUM = "enum"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    TEXT = "text"
    DATETIME = "datetime"


class AttributeSource(enum.StrEnum):
    PORTAL_METADATA = "portal_metadata"
    AI_EXTRACTION = "ai_extraction"
    DERIVED = "derived"


class Operator(enum.StrEnum):
    # money / integer
    LTE = "lte"
    GTE = "gte"
    BETWEEN = "between"
    # list
    IN = "in"
    NOT_IN = "not_in"
    INTERSECTS = "intersects"
    SUBSET_OF = "subset_of"
    # boolean
    EQ = "eq"
    # text
    CONTAINS_ANY = "contains_any"
    NOT_CONTAINS_ANY = "not_contains_any"
    # datetime
    WITHIN_DAYS = "within_days"
    AFTER = "after"


class Severity(enum.StrEnum):
    HARD = "hard"
    """Decides eligibility. A failure means the tender cannot be bid on."""
    SOFT = "soft"
    """Colours the recommendation only; never makes a tender ineligible."""


class OnMissing(enum.StrEnum):
    """What to do when the attribute cannot be determined.

    The default is ``verify`` for a reason: silently passing hides a
    disqualification until bid day, and silently failing buries a tender the
    company could have won. Both are worse than asking.
    """

    VERIFY = "verify"
    PASS = "pass"
    FAIL = "fail"


#: Operators each type accepts. The API publishes this so the builder cannot
#: offer a combination the engine would reject.
OPERATORS_BY_TYPE: dict[AttributeType, tuple[Operator, ...]] = {
    AttributeType.MONEY: (Operator.LTE, Operator.GTE, Operator.BETWEEN),
    AttributeType.INTEGER: (Operator.LTE, Operator.GTE, Operator.BETWEEN),
    AttributeType.LIST: (
        Operator.IN,
        Operator.NOT_IN,
        Operator.INTERSECTS,
        Operator.SUBSET_OF,
    ),
    AttributeType.ENUM: (Operator.IN, Operator.NOT_IN),
    AttributeType.BOOLEAN: (Operator.EQ,),
    AttributeType.TEXT: (Operator.CONTAINS_ANY, Operator.NOT_CONTAINS_ANY),
    AttributeType.DATETIME: (Operator.WITHIN_DAYS, Operator.AFTER),
}


@dataclass(frozen=True, slots=True)
class Attribute:
    key: str
    label: str
    type: AttributeType
    source: AttributeSource
    description: str
    #: Profile field this can be compared against, when one makes sense. Drives
    #: the "compare with our own capacity" shortcut in the builder.
    profile_field: str | None = None
    #: Overrides the type's default operator list.
    operators: tuple[Operator, ...] = ()

    @property
    def allowed_operators(self) -> tuple[Operator, ...]:
        return self.operators or OPERATORS_BY_TYPE[self.type]


ATTRIBUTES: tuple[Attribute, ...] = (
    Attribute(
        key="min_annual_turnover",
        label="Required annual turnover",
        type=AttributeType.MONEY,
        source=AttributeSource.AI_EXTRACTION,
        description="The minimum turnover a bidder must demonstrate.",
        profile_field="annual_turnover",
    ),
    Attribute(
        key="estimated_value",
        label="Contract value",
        type=AttributeType.MONEY,
        source=AttributeSource.PORTAL_METADATA,
        description="The published or extracted value of the contract.",
    ),
    Attribute(
        key="bid_security",
        label="Bid security",
        type=AttributeType.MONEY,
        source=AttributeSource.AI_EXTRACTION,
        description="Earnest money or bid bond the notice requires.",
    ),
    Attribute(
        key="required_certifications",
        label="Required certifications",
        type=AttributeType.LIST,
        source=AttributeSource.AI_EXTRACTION,
        description="Certifications the notice names as mandatory.",
        profile_field="certification_codes",
    ),
    Attribute(
        key="eligible_countries",
        label="Eligible bidder countries",
        type=AttributeType.LIST,
        source=AttributeSource.AI_EXTRACTION,
        description="Countries whose firms may bid. Empty means unrestricted.",
        profile_field="geographies",
    ),
    Attribute(
        key="sectors",
        label="Tender sectors",
        type=AttributeType.LIST,
        source=AttributeSource.AI_EXTRACTION,
        description="Sectors the work belongs to.",
        profile_field="sectors",
    ),
    Attribute(
        key="country",
        label="Tender country",
        type=AttributeType.ENUM,
        source=AttributeSource.PORTAL_METADATA,
        description="Where the contract is let.",
        profile_field="geographies",
    ),
    Attribute(
        key="procurement_method",
        label="Procurement method",
        type=AttributeType.ENUM,
        source=AttributeSource.PORTAL_METADATA,
        description="Open tendering, RFQ, direct procurement and so on.",
    ),
    Attribute(
        key="procurement_category",
        label="Category",
        type=AttributeType.ENUM,
        source=AttributeSource.PORTAL_METADATA,
        description="Goods, works, services or consulting.",
    ),
    Attribute(
        key="language",
        label="Notice language",
        type=AttributeType.ENUM,
        source=AttributeSource.PORTAL_METADATA,
        description="Language the notice is published in.",
    ),
    Attribute(
        key="min_years_experience",
        label="Years of experience required",
        type=AttributeType.INTEGER,
        source=AttributeSource.AI_EXTRACTION,
        description="Minimum years of relevant experience demanded.",
        profile_field="years_in_business",
    ),
    Attribute(
        key="similar_projects_required",
        label="Similar projects required",
        type=AttributeType.INTEGER,
        source=AttributeSource.AI_EXTRACTION,
        description="How many comparable contracts a bidder must show.",
        profile_field="past_project_count",
    ),
    Attribute(
        key="jv_allowed",
        label="Joint venture allowed",
        type=AttributeType.BOOLEAN,
        source=AttributeSource.AI_EXTRACTION,
        description="Whether a consortium or JV may bid.",
        profile_field="accepts_jv",
    ),
    Attribute(
        key="local_registration_required",
        label="Local registration required",
        type=AttributeType.BOOLEAN,
        source=AttributeSource.AI_EXTRACTION,
        description="Whether local incorporation or enlistment is mandatory.",
    ),
    Attribute(
        key="full_text",
        label="Anywhere in the notice",
        type=AttributeType.TEXT,
        source=AttributeSource.DERIVED,
        description="Title, summary and description combined.",
    ),
    Attribute(
        key="title",
        label="Notice title",
        type=AttributeType.TEXT,
        source=AttributeSource.PORTAL_METADATA,
        description="The published title.",
    ),
    Attribute(
        key="procuring_entity",
        label="Buyer",
        type=AttributeType.TEXT,
        source=AttributeSource.PORTAL_METADATA,
        description="The organisation letting the contract.",
    ),
    Attribute(
        key="deadline_at",
        label="Submission deadline",
        type=AttributeType.DATETIME,
        source=AttributeSource.PORTAL_METADATA,
        description="When bids are due.",
    ),
)

BY_KEY: dict[str, Attribute] = {attribute.key: attribute for attribute in ATTRIBUTES}


def get_attribute(key: str) -> Attribute | None:
    return BY_KEY.get(key)


@dataclass(frozen=True, slots=True)
class Preset:
    """A rule most customers want, phrased the way they would phrase it."""

    key: str
    label: str
    description: str
    attribute: str
    operator: Operator
    severity: Severity
    on_missing: OnMissing
    #: `{"source": "profile", "field": ...}` or `{"source": "literal", "data": ...}`
    value: dict[str, object] = field(default_factory=dict)


PRESETS: tuple[Preset, ...] = (
    Preset(
        key="turnover_within_capacity",
        label="Turnover requirement within our capacity",
        description="Skip tenders demanding more turnover than we can show.",
        attribute="min_annual_turnover",
        operator=Operator.LTE,
        severity=Severity.HARD,
        on_missing=OnMissing.VERIFY,
        value={"source": "profile", "field": "annual_turnover"},
    ),
    Preset(
        key="certifications_we_hold",
        label="We hold every certification required",
        description="Skip tenders requiring a certification we do not have.",
        attribute="required_certifications",
        operator=Operator.SUBSET_OF,
        severity=Severity.HARD,
        on_missing=OnMissing.PASS,
        value={"source": "profile", "field": "certification_codes"},
    ),
    Preset(
        key="eligible_countries_include_ours",
        label="Our country is eligible to bid",
        description="Skip tenders restricted to firms from elsewhere.",
        attribute="eligible_countries",
        operator=Operator.INTERSECTS,
        severity=Severity.HARD,
        on_missing=OnMissing.PASS,
        value={"source": "profile", "field": "geographies"},
    ),
    Preset(
        key="contract_value_in_range",
        label="Contract value in the range we bid",
        description="Skip contracts too small to be worth it or too large to deliver.",
        attribute="estimated_value",
        operator=Operator.BETWEEN,
        severity=Severity.SOFT,
        on_missing=OnMissing.PASS,
        value={"source": "literal", "data": {"min": None, "max": None}},
    ),
    Preset(
        key="exclude_keywords",
        label="Exclude work we do not do",
        description="Skip notices mentioning work outside our scope.",
        attribute="full_text",
        operator=Operator.NOT_CONTAINS_ANY,
        severity=Severity.HARD,
        on_missing=OnMissing.PASS,
        value={"source": "literal", "data": []},
    ),
    Preset(
        key="preferred_methods",
        label="Only procurement methods we bid",
        description="Skip methods we do not participate in.",
        attribute="procurement_method",
        operator=Operator.IN,
        severity=Severity.SOFT,
        on_missing=OnMissing.PASS,
        value={"source": "literal", "data": []},
    ),
    Preset(
        key="sectors_of_interest",
        label="Sectors we work in",
        description="Down-rank tenders outside our sectors.",
        attribute="sectors",
        operator=Operator.INTERSECTS,
        severity=Severity.SOFT,
        on_missing=OnMissing.PASS,
        value={"source": "profile", "field": "sectors"},
    ),
    Preset(
        key="jv_permitted",
        label="Joint ventures are allowed",
        description="Only relevant when we bid as part of a consortium.",
        attribute="jv_allowed",
        operator=Operator.EQ,
        severity=Severity.SOFT,
        on_missing=OnMissing.VERIFY,
        value={"source": "literal", "data": True},
    ),
    Preset(
        key="enough_time_to_bid",
        label="Enough time left to prepare a bid",
        description="Flag tenders closing sooner than we can realistically respond.",
        attribute="deadline_at",
        operator=Operator.AFTER,
        severity=Severity.SOFT,
        on_missing=OnMissing.VERIFY,
        value={"source": "literal", "data": {"days_from_now": 7}},
    ),
)

PRESETS_BY_KEY: dict[str, Preset] = {preset.key: preset for preset in PRESETS}
