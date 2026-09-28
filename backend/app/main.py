from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from sqlalchemy import text

from app.api.router import api_router
from app.core.config import settings
from app.core.logging import install_secret_filter
from app.db.session import engine

logger = logging.getLogger("jobhunter")


@asynccontextmanager
async def lifespan(_: FastAPI):
    install_secret_filter()
    settings.data_path.mkdir(parents=True, exist_ok=True)
    settings.cv_storage_path.mkdir(parents=True, exist_ok=True)
    logger.info("Job Hunter API started (env=%s)", settings.environment)
    yield
    engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title=f"{settings.app_name} API",
        version="0.1.0",
        description=(
            "Job Hunter API: user management, mailbox scanning, "
            "LLM scoring and notifications."
        ),
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "detail": {
                    "code": "validation_error",
                    "message": "Gönderilen veri geçersiz.",
                    "errors": [
                        {
                            "field": ".".join(str(part) for part in error["loc"][1:]),
                            "message": error["msg"],
                        }
                        for error in exc.errors()
                    ],
                }
            },
        )

    @app.get("/health", tags=["meta"])
    def health() -> dict:
        return {
            "status": "ok",
            "app": settings.app_name,
            "environment": settings.environment,
        }

    @app.get("/health/ready", tags=["meta"])
    def readiness() -> JSONResponse:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return JSONResponse(status_code=200, content={"status": "ready"})
        except Exception as exc:
            logger.warning("Readiness probe failed: %s", exc)
            return JSONResponse(
                status_code=503,
                content={"status": "not_ready", "detail": "Database unavailable"},
            )

    app.include_router(api_router)
    return app


app = create_app()
