"""Reading and editing the company profile.

Every write goes through :func:`touch_profile`, which bumps the version and
schedules a re-match. The version is what a stored match records, so bumping it
is precisely what tells the matcher "your inputs moved, score me again" — and
forgetting to bump it would leave a customer looking at grades computed against
a profile they have since replaced.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.schemas import Sector
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.core.time import utcnow
from app.jobs.queue import get_queue
from app.modules.profiles.models import (
    CompanyProfile,
    ProfileCertification,
    ProfilePastProject,
    ProfileService,
)
from app.modules.profiles.schemas import (
    CertificationIn,
    CompletenessRead,
    CompletenessSection,
    PastProjectIn,
    ProfileRead,
    ProfileUpdate,
    ServiceIn,
    canonical_certification,
)

logger = get_logger(__name__)

#: Debounce window for the re-match a profile edit triggers. Someone filling in
#: a form touches the profile many times in a minute; without this, each
#: keystroke-sized save would queue a full re-score of the pool.
REMATCH_DEBOUNCE_SECONDS = 30

#: Certifications customers ask about most, offered as suggestions. Not a
#: closed set — anything typed is accepted and canonicalised.
COMMON_CERTIFICATIONS = [
    "ISO 9001",
    "ISO 14001",
    "ISO 27001",
    "ISO 45001",
    "CMMI Level 3",
    "CMMI Level 5",
    "OHSAS 18001",
    "PMP",
    "Enlistment with PWD",
    "BASIS Membership",
]

#: Starting points for the services list, grouped loosely by the sectors the
#: matcher knows. Offered as suggestions only — a service is embedded and
#: compared by meaning, so anything typed is valid.
#:
#: The suggestions exist because a service is not free text in effect even
#: though it is in form: it is one of the vectors every grade is computed
#: against, and "netwrk integration" scores against nothing. Certifications
#: already had this list and services, which matter more to a grade, did not.
COMMON_SERVICES = [
    # it / telecom
    "Software development",
    "Web and mobile application development",
    "Systems integration",
    "Network integration",
    "Data centre design and build",
    "Cloud migration and managed hosting",
    "Cybersecurity assessment",
    "IT support and maintenance",
    "ERP implementation",
    "Data analytics and business intelligence",
    "Fibre optic network installation",
    # construction / works
    "Civil construction",
    "Road construction and maintenance",
    "Bridge construction",
    "Building construction",
    "Electrical installation",
    "Mechanical installation",
    "Plumbing and sanitary works",
    "Architectural design",
    "Structural engineering design",
    "Surveying and site investigation",
    # energy / water / environment
    "Solar power installation",
    "Power distribution works",
    "Water supply and distribution",
    "Water treatment plant construction",
    "Waste management",
    "Environmental impact assessment",
    "Irrigation works",
    # supply and services
    "Equipment supply and installation",
    "Medical equipment supply",
    "Laboratory equipment supply",
    "Furniture supply",
    "Vehicle supply and leasing",
    "Printing and publishing",
    "Facility management",
    "Security services",
    "Cleaning services",
    "Catering services",
    "Logistics and freight forwarding",
    "Warehousing and distribution",
    # consulting
    "Management consulting",
    "Feasibility study",
    "Monitoring and evaluation",
    "Training and capacity building",
    "Financial audit",
    "Procurement advisory",
    "Project management consultancy",
]


async def get_or_create_profile(session: AsyncSession, org_id: UUID) -> CompanyProfile:
    """One profile per organization, created empty on first read.

    Creating it lazily means the onboarding wizard and the settings page can
    both just PUT, without either needing a "create profile" step.
    """
    profile = await session.scalar(select(CompanyProfile).where(CompanyProfile.org_id == org_id))
    if profile is None:
        profile = CompanyProfile(org_id=org_id)
        session.add(profile)
        await session.flush()
        logger.info("profile_created", org_id=str(org_id))
    return profile


async def load_children(
    session: AsyncSession, profile_id: UUID
) -> tuple[list[ProfileService], list[ProfilePastProject], list[ProfileCertification]]:
    services = list(
        (
            await session.scalars(
                select(ProfileService)
                .where(ProfileService.profile_id == profile_id)
                .order_by(ProfileService.position, ProfileService.created_at)
            )
        ).all()
    )
    projects = list(
        (
            await session.scalars(
                select(ProfilePastProject)
                .where(ProfilePastProject.profile_id == profile_id)
                .order_by(ProfilePastProject.completed_on.desc().nulls_last())
            )
        ).all()
    )
    certifications = list(
        (
            await session.scalars(
                select(ProfileCertification)
                .where(ProfileCertification.profile_id == profile_id)
                .order_by(ProfileCertification.code)
            )
        ).all()
    )
    return services, projects, certifications


def _sections(
    profile: CompanyProfile,
    *,
    services: list[ProfileService],
    projects: list[ProfilePastProject],
    certifications: list[ProfileCertification],
) -> list[CompletenessSection]:
    """Weighted by how much each section actually improves matching.

    The overview and services carry the most weight because they are what get
    embedded; turnover and certifications matter for eligibility rather than
    for the score, so they are worth less here.
    """
    return [
        CompletenessSection(
            key="overview",
            label="Company overview",
            complete=bool(profile.overview and profile.overview.strip()),
            weight=25,
        ),
        CompletenessSection(key="services", label="Services", complete=bool(services), weight=25),
        CompletenessSection(
            key="sectors",
            label="Sectors and geographies",
            complete=bool(profile.sectors and profile.geographies),
            weight=15,
        ),
        CompletenessSection(
            key="past_projects", label="Past projects", complete=bool(projects), weight=15
        ),
        CompletenessSection(
            key="turnover",
            label="Annual turnover",
            complete=profile.annual_turnover is not None,
            weight=10,
        ),
        CompletenessSection(
            key="certifications",
            label="Certifications",
            complete=bool(certifications),
            weight=10,
        ),
    ]


def completeness(
    profile: CompanyProfile,
    *,
    services: list[ProfileService],
    projects: list[ProfilePastProject],
    certifications: list[ProfileCertification],
) -> CompletenessRead:
    sections = _sections(
        profile, services=services, projects=projects, certifications=certifications
    )
    score = sum(section.weight for section in sections if section.complete)
    missing = next((section for section in sections if not section.complete), None)
    return CompletenessRead(
        score=score,
        sections=sections,
        next_step=f"Add your {missing.label.lower()}." if missing else None,
    )


async def read_profile(session: AsyncSession, org_id: UUID) -> ProfileRead:
    profile = await get_or_create_profile(session, org_id)
    services, projects, certifications = await load_children(session, profile.id)
    return ProfileRead(
        **{
            column.name: getattr(profile, column.name)
            for column in CompanyProfile.__table__.columns
        },
        services=list(services),
        past_projects=list(projects),
        certifications=list(certifications),
    )


#: The score at which a profile has enough in it to match against, and so the
#: score at which pulling the portals for this organization is worth doing.
#: Paired with PROFILE_SYNC_THRESHOLD in the frontend's use-portal-sync.ts,
#: which is what warns a member that a sync will not grade anything yet.
WELCOME_SYNC_COMPLETENESS = 50


async def maybe_welcome_sync(session: AsyncSession, profile: CompanyProfile) -> str | None:
    """Pull the portals once, the first time a profile is worth matching.

    Someone who has just finished a profile expects to see the product work.
    What they actually see is whatever the last scheduled pass happened to
    leave, which on a quiet deployment is nothing — and the honest next step is
    the one thing they cannot be expected to know to go and do.

    Scoped to this organization, like any hand-pressed sync: the notices land
    in the shared pool for everyone, and only the tenant who just described
    themselves is re-scored on the spot.

    Stamped only when something was actually queued. The cooldown is
    deployment-wide, so a courtesy that collided with someone else's sync would
    otherwise spend this organization's single chance on a pass that never ran.
    """
    if profile.welcome_sync_at is not None:
        return None
    if profile.completeness < WELCOME_SYNC_COMPLETENESS:
        return None

    # Imported here: the tender service reaches back into profiles for
    # matching, and a module-level import would close the loop.
    from app.modules.tenders import service as tenders

    try:
        state = await tenders.sync_sources(session, org_id=profile.org_id)
    except Exception as exc:  # pragma: no cover - a courtesy must not fail a save
        logger.warning("welcome_sync_failed", org_id=str(profile.org_id), error=str(exc))
        return None

    if not state.queued:
        # Refused by the cooldown, or every portal was already mid-pass. Leave
        # the stamp off so the next save tries again.
        return None

    profile.welcome_sync_at = utcnow()
    await session.flush()
    logger.info(
        "welcome_sync_started",
        org_id=str(profile.org_id),
        completeness=profile.completeness,
        queued=state.queued,
    )
    return ",".join(state.queued)


async def touch_profile(session: AsyncSession, profile: CompanyProfile) -> None:
    """Record that the profile changed and refresh its completeness.

    Bumping the version is what invalidates every stored match's fingerprint.
    """
    services, projects, certifications = await load_children(session, profile.id)
    profile.completeness = completeness(
        profile, services=services, projects=projects, certifications=certifications
    ).score
    profile.version += 1
    await session.flush()
    await maybe_welcome_sync(session, profile)


async def schedule_rematch(org_id: UUID, *, reason: str = "profile_changed") -> str | None:
    """Queue a re-score, collapsing rapid edits into one run.

    The job id is derived from the org and a coarse time bucket, so ARQ treats
    repeated enqueues inside the window as the same job. A form being filled in
    therefore costs one re-match, not one per save.
    """
    try:
        queue = await get_queue()
        job = await queue.enqueue_job(
            "rematch_org",
            str(org_id),
            reason,
            _defer_by=REMATCH_DEBOUNCE_SECONDS,
            _job_id=f"rematch:{org_id}",
        )
    except Exception as exc:  # pragma: no cover - Redis down must not fail a save
        logger.warning("rematch_enqueue_failed", org_id=str(org_id), error=str(exc))
        return None
    # `enqueue_job` returns None when a job with this id is already queued,
    # which is the debounce working rather than a failure.
    return job.job_id if job else None


async def update_profile(
    session: AsyncSession, org_id: UUID, data: ProfileUpdate
) -> CompanyProfile:
    profile = await get_or_create_profile(session, org_id)
    patch = data.model_dump(exclude_unset=True)
    for field, value in patch.items():
        if field == "sectors" and value is not None:
            value = [sector.value if isinstance(sector, Sector) else sector for sector in value]
        setattr(profile, field, value)
    await touch_profile(session, profile)
    return profile


async def add_service(session: AsyncSession, org_id: UUID, data: ServiceIn) -> ProfileService:
    profile = await get_or_create_profile(session, org_id)
    service = ProfileService(
        profile_id=profile.id,
        name=data.name,
        description=data.description,
        sector=data.sector.value if data.sector else None,
        position=data.position,
    )
    session.add(service)
    await touch_profile(session, profile)
    return service


async def update_service(
    session: AsyncSession, org_id: UUID, service_id: UUID, data: ServiceIn
) -> ProfileService:
    profile = await get_or_create_profile(session, org_id)
    service = await _owned(session, ProfileService, service_id, profile.id, "Service")
    service.name = data.name
    service.description = data.description
    service.sector = data.sector.value if data.sector else None
    service.position = data.position
    await touch_profile(session, profile)
    return service


async def delete_service(session: AsyncSession, org_id: UUID, service_id: UUID) -> None:
    profile = await get_or_create_profile(session, org_id)
    service = await _owned(session, ProfileService, service_id, profile.id, "Service")
    await session.delete(service)
    await touch_profile(session, profile)


async def add_project(
    session: AsyncSession, org_id: UUID, data: PastProjectIn
) -> ProfilePastProject:
    profile = await get_or_create_profile(session, org_id)
    project = ProfilePastProject(
        profile_id=profile.id,
        **data.model_dump(exclude={"sector"}),
        sector=data.sector.value if data.sector else None,
    )
    session.add(project)
    await touch_profile(session, profile)
    return project


async def update_project(
    session: AsyncSession, org_id: UUID, project_id: UUID, data: PastProjectIn
) -> ProfilePastProject:
    profile = await get_or_create_profile(session, org_id)
    project = await _owned(session, ProfilePastProject, project_id, profile.id, "Project")
    for field, value in data.model_dump(exclude={"sector"}).items():
        setattr(project, field, value)
    project.sector = data.sector.value if data.sector else None
    await touch_profile(session, profile)
    return project


async def delete_project(session: AsyncSession, org_id: UUID, project_id: UUID) -> None:
    profile = await get_or_create_profile(session, org_id)
    project = await _owned(session, ProfilePastProject, project_id, profile.id, "Project")
    await session.delete(project)
    await touch_profile(session, profile)


async def add_certification(
    session: AsyncSession, org_id: UUID, data: CertificationIn
) -> ProfileCertification:
    """Add a credential, replacing any existing entry with the same code.

    Codes are canonicalised, so re-adding "ISO 9001:2015" over "ISO 9001"
    updates the label rather than creating a second row a rule would double-count.
    """
    profile = await get_or_create_profile(session, org_id)
    code = canonical_certification(data.label)

    existing = await session.scalar(
        select(ProfileCertification).where(
            ProfileCertification.profile_id == profile.id,
            ProfileCertification.code == code,
        )
    )
    if existing is not None:
        existing.label = data.label
        existing.issuer = data.issuer
        existing.valid_until = data.valid_until
        await touch_profile(session, profile)
        return existing

    certification = ProfileCertification(
        profile_id=profile.id,
        code=code,
        label=data.label,
        issuer=data.issuer,
        valid_until=data.valid_until,
    )
    session.add(certification)
    await touch_profile(session, profile)
    return certification


async def delete_certification(session: AsyncSession, org_id: UUID, certification_id: UUID) -> None:
    profile = await get_or_create_profile(session, org_id)
    certification = await _owned(
        session, ProfileCertification, certification_id, profile.id, "Certification"
    )
    await session.delete(certification)
    await touch_profile(session, profile)


async def _owned[T](
    session: AsyncSession, model: type[T], row_id: UUID, profile_id: UUID, label: str
) -> T:
    """Fetch a child row, refusing anything belonging to another tenant.

    The profile id comes from the access token, never the request, so a caller
    cannot reach another organization's rows by guessing an id.
    """
    row = await session.get(model, row_id)
    if row is None or getattr(row, "profile_id", None) != profile_id:
        raise NotFoundError(f"{label} not found.", code=f"{label.lower()}_not_found")
    return row
