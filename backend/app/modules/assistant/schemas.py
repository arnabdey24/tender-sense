"""Bounded contracts shared by text, voice, and the analysis workspace."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Language = Literal["auto", "en", "bn"]
ArtifactKind = Literal[
    "capabilities", "eligibility", "calculation", "checklist", "timeline", "scenario"
]


class Source(BaseModel):
    id: str
    label: str
    quote: str
    url: str | None = None


class AnalysisRow(BaseModel):
    label: str
    value: float | None = None
    baseline: float | None = None
    detail: str = ""
    status: str | None = None
    source_id: str | None = None


class Artifact(BaseModel):
    id: str
    version: int = 1
    kind: ArtifactKind
    title: str
    description: str
    rows: list[AnalysisRow] = Field(default_factory=list)
    formulas: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    unit: str = ""
    context_version: str
    created_at: datetime


class AnalyzeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: ArtifactKind
    adjustment_percent: float = Field(default=0, ge=-100, le=500, allow_inf_nan=False)


#: Pages the assistant is allowed to open. An allow-list, not a free path, so a
#: model can never be talked into navigating somewhere by quoted notice text.
AppPage = Literal[
    "dashboard",
    "today",
    "matches",
    "tenders",
    "pipeline",
    "notifications",
    "settings",
    "settings/profile",
    "settings/rules",
    "settings/members",
    "settings/organization",
    "settings/notifications",
    "settings/sources",
    "account",
]


class NavigateFilters(BaseModel):
    """Filters the assistant may apply to a list it opens.

    Every field is a closed set matching the route's own search schema, so a
    model can express "open works tenders that are still open" but cannot invent
    a filter the page does not have or smuggle arbitrary text into the URL. The
    free-text search is the one open field and it is length-bounded.
    """

    model_config = ConfigDict(extra="forbid")

    #: Tender pool.
    q: str | None = Field(default=None, max_length=120)
    category: Literal["goods", "works", "services", "consulting"] | None = None
    status: Literal["open", "closed", "cancelled", "awarded"] | None = None
    source: str | None = Field(default=None, max_length=40)
    open_only: bool | None = None

    #: Matches.
    grade: Literal["S", "A", "B", "C"] | None = None
    eligibility: Literal["eligible", "needs_verification", "ineligible"] | None = None
    recommendation: Literal["bid", "hold", "skip"] | None = None

    #: Both, though each page accepts a different subset; the client drops any
    #: value its own route does not understand.
    sort: (
        Literal[
            "published_at",
            "deadline_at",
            "title",
            "estimated_value",
            "similarity",
            "created_at",
        ]
        | None
    ) = None


class NavigateInput(BaseModel):
    """Ask the client to move the workspace. Never changes business data."""

    model_config = ConfigDict(extra="forbid")
    page: AppPage | None = None
    tender_id: UUID | None = None
    filters: NavigateFilters | None = None
    reason: str = Field(default="", max_length=200)


class ConversationCreate(BaseModel):
    #: Absent for a workspace conversation — see the 0011 migration.
    tender_id: UUID | None = None


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    tender_id: UUID | None
    title: str
    created_at: datetime
    updated_at: datetime


class TurnInput(BaseModel):
    request_id: UUID
    text: str = Field(min_length=1, max_length=8000)
    language: Language = "auto"
    #: Where the user is standing when they ask. Lets "explain this" resolve, and
    #: stops the assistant navigating somebody to the page they are already on.
    page: str | None = Field(default=None, max_length=120)
    artifact: AnalyzeInput | None = None
    active_artifact: ArtifactKind | None = None


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    request_id: UUID
    role: Literal["user", "assistant"]
    content: str
    status: str
    sources: list[Source] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)
    context_version: str = ""
    created_at: datetime


class ConversationDetail(ConversationRead):
    messages: list[MessageRead]


class Capabilities(BaseModel):
    enabled: bool
    voice_enabled: bool
    mode: Literal["gemini", "demo", "unavailable"]
    voice_max_seconds: int
    voice_unavailable_reason: (
        Literal["assistant_off", "voice_off", "no_key", "provider_not_gemini"] | None
    ) = None
    """Why live voice is off, when it is.

    The interface had only the fact, and rendered it as a greyed button with a
    tooltip — invisible on a touch screen, and silent about whether this is a
    deployment that has voice switched off, one missing a key, or one running
    the offline stub. Those want different sentences, and one of them wants an
    operator rather than the person reading it.

    Names a setting, never a value, so it stays safe to hand to any member.
    """


class VoiceTicket(BaseModel):
    ticket: str
    expires_in: int = 30


class Event(BaseModel):
    schema_version: int = 1
    type: str
    turn_id: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
