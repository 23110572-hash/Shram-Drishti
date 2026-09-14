"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import auth, documents, establishments, findings, health, rules
from app.config import Settings, get_settings
from app.db import check_connection
from app.logging_setup import configure_logging
from app.middleware import REQUEST_ID_HEADER, RequestContextMiddleware
from app.services import jobs as job_service

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings

    logger.info(
        "starting up",
        extra={
            "version": __version__,
            "environment": settings.environment.value,
            "database": settings.safe_database_url(),
        },
    )

    if not check_connection():
        # Warn rather than crash: /readyz will report not_ready, which is more
        # useful than a process that will not boot at all.
        logger.warning("database unreachable at startup; /readyz will report not_ready")

    # Rule packs are loaded and validated at startup so a broken expression or a
    # missing citation fails here, loudly, rather than halfway through an
    # inspection on a background thread.
    try:
        from app.rules.loader import get_rules

        loaded = get_rules()
        errors = [issue for issue in loaded.issues if issue.level == "error"]
        logger.info(
            "rule packs loaded",
            extra={
                "packs": len(loaded.packs),
                "rules": len(loaded.all_rules),
                "pending_notification": len(loaded.rules_pending_notification),
                "errors": len(errors),
            },
        )
        for issue in errors[:20]:
            # Not "message": the logging module reserves that attribute on a
            # LogRecord and raises KeyError if extra tries to overwrite it.
            logger.error(
                "rule pack error",
                extra={"rule_id": issue.rule_id, "detail": issue.message},
            )
        if loaded.rules_pending_notification:
            # Said plainly at startup. An operator should know which obligations
            # rest on a number the Act left to a notification nobody has obtained
            # yet, before anyone enforces on one.
            logger.warning(
                "%d rule(s) rely on a number the Act leaves to the appropriate "
                "Government, where that notification has not been obtained; "
                "findings from these are flagged and weighted lightly",
                len(loaded.rules_pending_notification),
            )
    except Exception:
        logger.exception("rule packs could not be loaded")

    job_service.start_worker()
    try:
        yield
    finally:
        job_service.stop_worker()
        logger.info("shutting down")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(level=settings.log_level, fmt=settings.log_format)

    app = FastAPI(
        title=settings.app_name,
        description=(
            "AI Smart Inspection System for Labour Code Compliance.\n\n"
            "Documents are read by OCR and a vision model together, then checked "
            "so that every figure can be traced to a cell on the page. "
            "Compliance verdicts are decided by deterministic rules with "
            "statutory citations; the model's own observations are advisory and "
            "never affect a compliance score."
        ),
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )
    app.state.settings = settings

    # ------------------------------------------------------------- middleware
    # Order matters and is not arbitrary. Starlette treats the last middleware
    # added as the outermost, so CORS must be registered *after* the request
    # context middleware to end up wrapping it.
    #
    # That is what lets a 500 reach a browser on another origin. Unhandled
    # exceptions are converted to a response inside RequestContextMiddleware; CORS
    # then adds its headers to that response on the way out. Reverse these two and
    # every server error becomes an opaque "cannot reach the API" in the UI,
    # because the browser blocks a cross-origin response with no CORS headers and
    # fetch cannot tell that apart from the host being down.
    app.add_middleware(RequestContextMiddleware)

    # Only added when origins are configured. Deployed split across two hosts —
    # frontend on one, API on another — the browser needs this; run locally behind
    # the Vite proxy it is same-origin and unnecessary.
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type"],
            expose_headers=[REQUEST_ID_HEADER],
        )
        logger.info(
            "CORS enabled", extra={"origins": settings.cors_origins}
        )

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(documents.router)
    app.include_router(findings.router)
    app.include_router(establishments.router)
    app.include_router(rules.router)

    return app


app = create_app()
