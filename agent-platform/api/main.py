from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.core.errors import register_exception_handlers
from api.db.postgres import install_postgres
from api.events.outbox_signaler import OutboxSignaler
from api.events.redis_bus import build_outbox_signal_bus
from api.routes.incident_chat import router as incident_chat_router
from api.routes.incidents import router as incidents_router
from api.routes.telemetry import router as telemetry_router


@asynccontextmanager
async def lifespan(app: FastAPI):
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
    register_exception_handlers(app)
    app.include_router(telemetry_router)
    app.include_router(incident_chat_router)
    app.include_router(incidents_router)
    return app


app = create_app()
