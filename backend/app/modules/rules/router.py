"""Bidding criteria: the catalogue, the rule set, and previewing a draft.

Reads are open to any member; writes are admin-only, because a rule decides
what the whole organization is shown. Saving writes a new version and schedules
a re-match, so the feed reflects the new criteria without anyone asking.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Body, Path, Query

from app.core.deps import CurrentOrg, DbSession, RequireOrgAdmin
from app.core.exceptions import NotFoundError
from app.modules.profiles.service import get_or_create_profile, schedule_rematch
from app.modules.rules import preview as preview_module
from app.modules.rules import service
from app.modules.rules.catalogue import (
    ATTRIBUTES,
    OPERATORS_BY_TYPE,
    PRESETS,
    OnMissing,
    Operator,
    Severity,
)
from app.modules.rules.schemas import (
    CatalogueAttribute,
    CatalogueOperator,
    CataloguePreset,
    RuleCatalogue,
    RulePreview,
    RuleSetDefinition,
    RuleSetRead,
    RuleSetVersionRead,
    RuleSetWrite,
    RuleTestResult,
    RuleValidationResult,
)

router = APIRouter(tags=["rules"])

VersionId = Annotated[UUID, Path(description="Rule set version identifier")]
TenderId = Annotated[UUID, Path(description="Tender identifier")]

#: How each operator's `value` must be shaped, so the builder renders the right
#: input rather than guessing from the operator's name.
_VALUE_SHAPES: dict[Operator, str] = {
    Operator.LTE: "scalar",
    Operator.GTE: "scalar",
    Operator.BETWEEN: "range",
    Operator.IN: "list",
    Operator.NOT_IN: "list",
    Operator.INTERSECTS: "list",
    Operator.SUBSET_OF: "list",
    Operator.EQ: "boolean",
    Operator.CONTAINS_ANY: "list",
    Operator.NOT_CONTAINS_ANY: "list",
    Operator.WITHIN_DAYS: "days",
    Operator.AFTER: "days",
}

_OPERATOR_LABELS: dict[Operator, str] = {
    Operator.LTE: "is at most",
    Operator.GTE: "is at least",
    Operator.BETWEEN: "is between",
    Operator.IN: "is one of",
    Operator.NOT_IN: "is not one of",
    Operator.INTERSECTS: "overlaps with",
    Operator.SUBSET_OF: "is fully covered by",
    Operator.EQ: "is",
    Operator.CONTAINS_ANY: "mentions any of",
    Operator.NOT_CONTAINS_ANY: "mentions none of",
    Operator.WITHIN_DAYS: "is within",
    Operator.AFTER: "is at least this far away",
}


@router.get("/rules/catalogue", response_model=RuleCatalogue, summary="What rules can say")
async def read_catalogue(_: CurrentOrg) -> RuleCatalogue:
    """Everything the builder needs to render itself.

    Served from the backend so the UI cannot offer an attribute or operator the
    engine would reject.
    """
    return RuleCatalogue(
        attributes=[
            CatalogueAttribute(
                key=attribute.key,
                label=attribute.label,
                type=attribute.type,
                source=attribute.source.value,
                description=attribute.description,
                profile_field=attribute.profile_field,
                operators=list(attribute.allowed_operators),
            )
            for attribute in ATTRIBUTES
        ],
        operators=[
            CatalogueOperator(
                key=operator,
                label=_OPERATOR_LABELS[operator],
                value_shape=_VALUE_SHAPES[operator],
            )
            for operators in OPERATORS_BY_TYPE.values()
            for operator in operators
            if operator in _VALUE_SHAPES
        ],
        presets=[
            CataloguePreset(
                key=preset.key,
                label=preset.label,
                description=preset.description,
                attribute=preset.attribute,
                operator=preset.operator,
                severity=preset.severity,
                on_missing=preset.on_missing,
                value=dict(preset.value),
            )
            for preset in PRESETS
        ],
        severities=[severity.value for severity in Severity],
        on_missing_options=[option.value for option in OnMissing],
    )


@router.get("/rules/schema", summary="JSON Schema for a rule set")
async def read_schema(_: CurrentOrg) -> dict[str, Any]:
    """Generated from the same models the engine validates with, so the builder
    can check a draft client-side and get the same answer."""
    return RuleSetDefinition.model_json_schema()


@router.post("/rules/validate", response_model=RuleValidationResult, summary="Check a draft")
async def validate(
    _: CurrentOrg, payload: Annotated[dict[str, Any], Body()]
) -> RuleValidationResult:
    """Validate without saving. Errors come back per rule so the builder can
    mark the offending row rather than the whole form."""
    return service.validate_definition(payload)


@router.get("/rule-sets/current", response_model=RuleSetRead, summary="The active rule set")
async def read_current(ctx: CurrentOrg, db: DbSession) -> RuleSetRead:
    rule_set = await service.get_or_create_rule_set(db, ctx.org_id)
    version = await service.active_version(db, ctx.org_id)
    return RuleSetRead(
        id=rule_set.id,
        name=rule_set.name,
        is_active=rule_set.is_active,
        version_number=version.version_number if version else 0,
        definition=service.definition_of(version),
        created_at=rule_set.created_at,
        updated_at=rule_set.updated_at,
    )


@router.put("/rule-sets/current", response_model=RuleSetRead, summary="Save new criteria")
async def save_current(data: RuleSetWrite, ctx: RequireOrgAdmin, db: DbSession) -> RuleSetRead:
    """Write a new version, make it active, and re-score the open pool.

    The previous version is kept: every match records the version that graded
    it, so the reasoning behind an old verdict stays reconstructable.
    """
    version = await service.save_version(
        db,
        org_id=ctx.org_id,
        definition=data.definition,
        name=data.name,
        note=data.note,
        created_by_id=ctx.user.id,
    )
    rule_set = await service.get_or_create_rule_set(db, ctx.org_id)
    await schedule_rematch(ctx.org_id, reason="rules_changed")
    return RuleSetRead(
        id=rule_set.id,
        name=rule_set.name,
        is_active=rule_set.is_active,
        version_number=version.version_number,
        definition=data.definition,
        created_at=rule_set.created_at,
        updated_at=rule_set.updated_at,
    )


@router.get(
    "/rule-sets/current/versions",
    response_model=list[RuleSetVersionRead],
    summary="Version history",
)
async def list_versions(ctx: CurrentOrg, db: DbSession) -> list[RuleSetVersionRead]:
    rule_set = await service.get_or_create_rule_set(db, ctx.org_id)
    return [
        RuleSetVersionRead(
            id=version.id,
            version_number=version.version_number,
            definition=service.definition_of(version),
            created_at=version.created_at,
            note=version.note,
        )
        for version in await service.list_versions(db, rule_set.id)
    ]


@router.post(
    "/rule-sets/current/versions/{version_id}/activate",
    response_model=RuleSetVersionRead,
    summary="Roll back to a version",
)
async def activate(
    version_id: VersionId, ctx: RequireOrgAdmin, db: DbSession
) -> RuleSetVersionRead:
    """Point the rule set at an earlier version and re-score."""
    version = await service.activate_version(db, org_id=ctx.org_id, version_id=version_id)
    await schedule_rematch(ctx.org_id, reason="rules_rolled_back")
    return RuleSetVersionRead(
        id=version.id,
        version_number=version.version_number,
        definition=service.definition_of(version),
        created_at=version.created_at,
        note=version.note,
    )


@router.post("/rule-sets/preview", response_model=RulePreview, summary="Try a draft")
async def preview_draft(
    data: RuleSetWrite,
    ctx: CurrentOrg,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=preview_module.MAX_PREVIEW_TENDERS)] = 500,
) -> RulePreview:
    """Run a draft over the open pool without saving it.

    Per-rule counts are the useful part: "42 became ineligible" is alarming but
    useless, while "the certification rule rejected 42" names the line to relax.
    """
    profile = await get_or_create_profile(db, ctx.org_id)
    return await preview_module.preview(
        db, definition=data.definition, profile=profile, limit=limit
    )


@router.post(
    "/rule-sets/test/{tender_id}",
    response_model=RuleTestResult,
    summary="Try a draft against one tender",
)
async def test_draft(
    tender_id: TenderId, data: RuleSetWrite, ctx: CurrentOrg, db: DbSession
) -> RuleTestResult:
    """Answers "why did this particular tender fail?" rule by rule."""
    profile = await get_or_create_profile(db, ctx.org_id)
    result = await preview_module.test_against_tender(
        db, definition=data.definition, profile=profile, tender_id=tender_id
    )
    if result is None:
        raise NotFoundError("Tender not found.", code="tender_not_found")
    return result
