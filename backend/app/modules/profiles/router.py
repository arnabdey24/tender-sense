"""The organization's capability profile.

Reads are open to any member; writes are admin-only, because the profile decides
what the whole organization sees in its feed. Every write schedules a re-match.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Path, status

from app.ai.schemas import Sector
from app.core.deps import CurrentOrg, DbSession, RequireOrgAdmin
from app.core.rate_limit import limit_org_work
from app.modules.profiles import service
from app.modules.profiles.schemas import (
    CertificationIn,
    CertificationRead,
    CompletenessRead,
    PastProjectIn,
    PastProjectRead,
    ProfileRead,
    ProfileUpdate,
    RematchResponse,
    ServiceIn,
    ServiceRead,
    TaxonomiesRead,
)

router = APIRouter(tags=["profile"])

ServiceId = Annotated[UUID, Path(description="Service identifier")]
ProjectId = Annotated[UUID, Path(description="Past project identifier")]
CertificationId = Annotated[UUID, Path(description="Certification identifier")]


async def _rematch(org_id: UUID, reason: str = "profile_changed") -> RematchResponse:
    job_id = await service.schedule_rematch(org_id, reason=reason)
    return RematchResponse(enqueued=job_id is not None, job_id=job_id, reason=reason)


@router.get("/profile", response_model=ProfileRead, summary="Read the profile")
async def read_profile(ctx: CurrentOrg, db: DbSession) -> ProfileRead:
    """The organization's capability profile, created empty on first read."""
    return await service.read_profile(db, ctx.org_id)


@router.put("/profile", response_model=ProfileRead, summary="Update the profile")
async def update_profile(data: ProfileUpdate, ctx: RequireOrgAdmin, db: DbSession) -> ProfileRead:
    """Update the profile and schedule a re-match of the open pool."""
    await service.update_profile(db, ctx.org_id, data)
    result = await service.read_profile(db, ctx.org_id)
    await service.schedule_rematch(ctx.org_id)
    return result


@router.get(
    "/profile/completeness",
    response_model=CompletenessRead,
    summary="How complete the profile is",
)
async def read_completeness(ctx: CurrentOrg, db: DbSession) -> CompletenessRead:
    """A weighted score plus the next section worth filling in."""
    profile = await service.get_or_create_profile(db, ctx.org_id)
    services, projects, certifications = await service.load_children(db, profile.id)
    return service.completeness(
        profile, services=services, projects=projects, certifications=certifications
    )


@router.post("/profile/rematch", response_model=RematchResponse, summary="Re-score now")
async def trigger_rematch(ctx: RequireOrgAdmin) -> RematchResponse:
    """Queue a re-score without changing anything.

    Repeated calls inside the debounce window collapse into one run, so the
    limit here is about the queue rather than the work: it stops an impatient
    admin filling it with jobs that will each re-score the whole open pool.
    """
    await limit_org_work(ctx.org_id, operation="rematch", limit=10, window_seconds=3600)
    return await _rematch(ctx.org_id, reason="manual")


@router.get("/taxonomies", response_model=TaxonomiesRead, summary="Profile option lists")
async def read_taxonomies(_: CurrentOrg) -> TaxonomiesRead:
    """Served from the backend so the forms cannot offer a sector the matcher
    does not understand."""
    return TaxonomiesRead(
        sectors=[
            {"value": sector.value, "label": sector.value.replace("_", " ").title()}
            for sector in Sector
        ],
        common_certifications=service.COMMON_CERTIFICATIONS,
        common_services=service.COMMON_SERVICES,
    )


# -- services ---------------------------------------------------------------


@router.post(
    "/profile/services",
    response_model=ServiceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a service",
)
async def add_service(data: ServiceIn, ctx: RequireOrgAdmin, db: DbSession) -> ServiceRead:
    return ServiceRead.model_validate(await service.add_service(db, ctx.org_id, data))


@router.put("/profile/services/{service_id}", response_model=ServiceRead)
async def update_service(
    service_id: ServiceId, data: ServiceIn, ctx: RequireOrgAdmin, db: DbSession
) -> ServiceRead:
    return ServiceRead.model_validate(
        await service.update_service(db, ctx.org_id, service_id, data)
    )


@router.delete("/profile/services/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service(service_id: ServiceId, ctx: RequireOrgAdmin, db: DbSession) -> None:
    """Removing a service also drops its embedding, so it stops scoring."""
    await service.delete_service(db, ctx.org_id, service_id)


# -- past projects ----------------------------------------------------------


@router.post(
    "/profile/projects",
    response_model=PastProjectRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a past project",
)
async def add_project(data: PastProjectIn, ctx: RequireOrgAdmin, db: DbSession) -> PastProjectRead:
    return PastProjectRead.model_validate(await service.add_project(db, ctx.org_id, data))


@router.put("/profile/projects/{project_id}", response_model=PastProjectRead)
async def update_project(
    project_id: ProjectId, data: PastProjectIn, ctx: RequireOrgAdmin, db: DbSession
) -> PastProjectRead:
    return PastProjectRead.model_validate(
        await service.update_project(db, ctx.org_id, project_id, data)
    )


@router.delete("/profile/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: ProjectId, ctx: RequireOrgAdmin, db: DbSession) -> None:
    await service.delete_project(db, ctx.org_id, project_id)


# -- certifications ---------------------------------------------------------


@router.post(
    "/profile/certifications",
    response_model=CertificationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a certification",
)
async def add_certification(
    data: CertificationIn, ctx: RequireOrgAdmin, db: DbSession
) -> CertificationRead:
    """Codes are canonicalised, so "ISO 9001" and "iso-9001" are one entry."""
    return CertificationRead.model_validate(await service.add_certification(db, ctx.org_id, data))


@router.delete("/profile/certifications/{certification_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_certification(
    certification_id: CertificationId, ctx: RequireOrgAdmin, db: DbSession
) -> None:
    await service.delete_certification(db, ctx.org_id, certification_id)
