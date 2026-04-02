# Stimpact Python SDK

The Python SDK sends runtime exceptions to the Stimpact agent platform using a project-scoped API key.

## Install

```sh
pip install stimpact-sdk
```

## Basic usage

```python
from stimpact_sdk import StimpactClient

client = StimpactClient.from_env(
    service="billing-api",
    environment="production",
)

try:
    charge_customer()
except Exception as exc:
    client.capture_exception(
        exc,
        request={"method": "POST", "url": "/api/charge"},
    )
    raise
```

## Environment variables

- `STIMPACT_BASE_URL`
- `STIMPACT_PROJECT_ID`
- `STIMPACT_API_KEY`
- `STIMPACT_SERVICE`
- `STIMPACT_ENVIRONMENT`
