"""Aggregates every module router under the versioned API prefix."""

from __future__ import annotations

from fastapi import APIRouter

from app.modules.admin.health import router as health_router
from app.modules.auth.router import router as auth_router
from app.modules.orgs.router import router as orgs_router
from app.modules.tenders.router import router as tenders_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(orgs_router)
api_router.include_router(tenders_router)
