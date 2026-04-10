from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.core.config import get_telemetry_cors_allowed_origins, validate_runtime_configuration
from api.core.errors import register_exception_handlers
from api.db.postgres import install_postgres
from api.events.outbox_signaler import OutboxSignaler
from api.events.redis_bus import build_outbox_signal_bus
from api.middleware.telemetry_cors import install_telemetry_cors_middleware
from api.observability import RequestObservabilityMiddleware, configure_logging
from api.routes.auth import router as auth_router
from api.routes.control_plane import public_router as provider_callback_router
from api.routes.control_plane import project_router as project_control_plane_router
from api.routes.control_plane import router as control_plane_router
from api.routes.health import router as health_router
from api.routes.incident_chat import router as incident_chat_router
from api.routes.incidents import router as incidents_router
from api.routes.telemetry import router as telemetry_router
from services.telemetry_origin_registry import TelemetryOriginRegistry


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    validate_runtime_configuration(runtime="api")
    postgres = install_postgres(app)
    outbox_signal_bus = build_outbox_signal_bus()
    app.state.outbox_signaler = OutboxSignaler(outbox_signal_bus)
    app.state.outbox_signal_bus = outbox_signal_bus

    await postgres.connect()
    try:
        yield
    finally:
        await outbox_signal_bus.close()
        await postgres.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Agent Platform API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.telemetry_origin_registry = TelemetryOriginRegistry(
        pool_getter=lambda: getattr(getattr(app.state, "postgres", None), "pool", None),
        fallback_origins=get_telemetry_cors_allowed_origins(),
    )
    register_exception_handlers(app)
    install_telemetry_cors_middleware(app)
    app.add_middleware(RequestObservabilityMiddleware)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(telemetry_router)
    app.include_router(incident_chat_router)
    app.include_router(incidents_router)
    app.include_router(control_plane_router)
    app.include_router(project_control_plane_router)
    app.include_router(provider_callback_router)
    return app


app = create_app()
