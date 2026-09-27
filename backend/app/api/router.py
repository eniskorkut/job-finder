from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import verify_csrf
from app.api.v1 import (
    auth,
    cvs,
    integrations,
    jobs,
    me,
    notifications,
    preferences,
    sync,
)

api_router = APIRouter(prefix="/api/v1", dependencies=[Depends(verify_csrf)])

api_router.include_router(auth.router)
api_router.include_router(me.router)
api_router.include_router(preferences.router)
api_router.include_router(cvs.router)
api_router.include_router(jobs.router)
api_router.include_router(integrations.router)
api_router.include_router(sync.router)
api_router.include_router(notifications.router)

__all__ = ["api_router"]
