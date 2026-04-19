from __future__ import annotations

from .client import StimpactClient


def install_stimpact(app, *, service: str, environment: str = "production") -> StimpactClient:
    client = StimpactClient.from_env(
        service=service,
        environment=environment,
    )
    app.state.stimpact_heartbeat = client.start_heartbeat()

    @app.middleware("http")
    async def stimpact_capture_middleware(request, call_next):
        try:
            return await call_next(request)
        except Exception as exc:
            client.capture_exception(
                exc,
                request={
                    "method": request.method,
                    "url": str(request.url),
                },
            )
            raise

    return client
