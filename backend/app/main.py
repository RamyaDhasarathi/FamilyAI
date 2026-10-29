"""Main FastAPI application for Family OS."""
from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    agents,
    approvals,
    auth,
    families,
    governance,
    health,
    mobile_use,
    purchases,
    voice,
)
from app.core.config import get_settings
from app.core.exceptions import AppError, app_error_handler, generic_error_handler

logger = logging.getLogger("family_os")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting %s %s [%s]", settings.APP_NAME, settings.APP_VERSION, settings.APP_ENV)
    yield
    logger.info("Shutting down %s", settings.APP_NAME)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        lifespan=lifespan,
        docs_url="/docs" if settings.is_development else None,
        redoc_url="/redoc" if settings.is_development else None,
    )

    # CORS configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Correlation ID middleware
    @app.middleware("http")
    async def correlation_middleware(request: Request, call_next):
        correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
        request.state.correlation_id = correlation_id
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response

    # Exception handlers
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(Exception, generic_error_handler)

    prefix = settings.API_V1_PREFIX
    # Include API Routers
    app.include_router(health.router, tags=["health"])
    app.include_router(auth.router, prefix=f"{prefix}/auth", tags=["auth"])
    app.include_router(families.router, prefix=f"{prefix}/families", tags=["families"])
    app.include_router(governance.router, prefix=f"{prefix}/governance", tags=["governance"])
    app.include_router(agents.router, prefix=prefix, tags=["agents"])
    app.include_router(purchases.router, prefix=f"{prefix}/purchases", tags=["purchases"])
    app.include_router(approvals.router, prefix=f"{prefix}/approvals", tags=["approvals"])
    app.include_router(mobile_use.router, prefix=f"{prefix}/mobile-use", tags=["mobile_use"])
    app.include_router(voice.router, prefix=f"{prefix}/voice", tags=["voice"])

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.is_development,
        log_level="info",
    )
