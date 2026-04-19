from __future__ import annotations

from flask import got_request_exception, request

from .client import StimpactClient


def install_stimpact(app, *, service: str, environment: str = "production") -> StimpactClient:
    client = StimpactClient.from_env(
        service=service,
        environment=environment,
    )
    app.extensions["stimpact_heartbeat"] = client.start_heartbeat()

    def _capture(sender, exception, **extra):
        client.capture_exception(
            exception,
            request={
                "method": request.method,
                "url": request.url,
            },
        )

    got_request_exception.connect(_capture, app)
    return client
