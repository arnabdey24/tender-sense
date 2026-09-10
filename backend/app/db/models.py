"""Single import point for every ORM model.

Alembic autogenerate and the test bootstrap import this module, so each new
model must be re-exported here or its table will be silently dropped from
generated migrations.
"""

from __future__ import annotations

from app.db.base import Base
from app.modules.auth.models import AuthToken, RefreshSession, TokenPurpose
from app.modules.matching.models import (
    EligibilityStatus,
    ExplanationKind,
    MatchGrade,
    MatchingConfig,
    Recommendation,
    TenderMatch,
    TenderMatchHistory,
    Urgency,
)
from app.modules.notifications.models import EmailOutbox, EmailStatus
from app.modules.orgs.models import (
    Invitation,
    Membership,
    MembershipStatus,
    Organization,
    OrgRole,
)
from app.modules.profiles.models import (
    CompanyProfile,
    ProfileCertification,
    ProfileEmbedding,
    ProfileFacet,
    ProfilePastProject,
    ProfileService,
)
from app.modules.rules.models import (
    FxRate,
    OverrideVerdict,
    RuleOverride,
    RuleSet,
    RuleSetVersion,
)
from app.modules.tenders.models import (
    DocumentKind,
    EmbeddingChunk,
    ExtractionStatus,
    ProcurementCategory,
    SourceHealth,
    Tender,
    TenderDocument,
    TenderEmbedding,
    TenderExtraction,
    TenderSource,
    TenderStatus,
)
from app.modules.users.models import OAuthAccount, User

__all__ = [
    "AuthToken",
    "Base",
    "CompanyProfile",
    "DocumentKind",
    "EligibilityStatus",
    "EmailOutbox",
    "EmailStatus",
    "EmbeddingChunk",
    "ExplanationKind",
    "ExtractionStatus",
    "FxRate",
    "Invitation",
    "MatchGrade",
    "MatchingConfig",
    "Membership",
    "MembershipStatus",
    "OAuthAccount",
    "OrgRole",
    "Organization",
    "OverrideVerdict",
    "ProcurementCategory",
    "ProfileCertification",
    "ProfileEmbedding",
    "ProfileFacet",
    "ProfilePastProject",
    "ProfileService",
    "Recommendation",
    "RefreshSession",
    "RuleOverride",
    "RuleSet",
    "RuleSetVersion",
    "SourceHealth",
    "Tender",
    "TenderDocument",
    "TenderEmbedding",
    "TenderExtraction",
    "TenderMatch",
    "TenderMatchHistory",
    "TenderSource",
    "TenderStatus",
    "TokenPurpose",
    "Urgency",
    "User",
]
