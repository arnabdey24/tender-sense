"""Aggregates every module router under the versioned API prefix."""

from __future__ import annotations

from fastapi import APIRouter

from app.modules.admin.health import router as health_router
from app.modules.admin.router import router as admin_router
from app.modules.assistant import voice as _assistant_voice  # noqa: F401
from app.modules.assistant.router import router as assistant_router
from app.modules.auth.router import router as auth_router
from app.modules.decisions.router import router as decisions_router
from app.modules.matching.router import router as matches_router
from app.modules.notifications.router import router as notifications_router
from app.modules.orgs.router import router as orgs_router
from app.modules.profiles.router import router as profiles_router
from app.modules.rules.router import router as rules_router
from app.modules.tenders.router import router as tenders_router
from app.modules.users.router import router as users_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(assistant_router)
api_router.include_router(users_router)
api_router.include_router(orgs_router)
api_router.include_router(profiles_router)
api_router.include_router(tenders_router)
api_router.include_router(matches_router)
api_router.include_router(rules_router)
api_router.include_router(decisions_router)
api_router.include_router(notifications_router)
api_router.include_router(admin_router)
