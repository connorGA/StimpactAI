from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ENV_PATH = REPO_ROOT / ".env"

load_dotenv(DEFAULT_ENV_PATH)


def get_bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_database_url() -> str | None:
    return os.getenv("DATABASE_URL")


def get_openai_api_key() -> str | None:
    value = os.getenv("OPENAI_API_KEY")
    if value is None:
        return None

    normalized = value.strip()
    return normalized or None


def get_openai_model() -> str:
    value = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()
    return value or "gpt-4.1-mini"


def get_redis_url() -> str | None:
    value = os.getenv("REDIS_URL")
    if value is None:
        return None

    normalized = value.strip()
    if not normalized:
        return None

    if "://" not in normalized:
        return f"redis://{normalized}"

    return normalized


def get_outbox_signal_stream() -> str:
    return os.getenv("AGENT_PLATFORM_OUTBOX_SIGNAL_STREAM", "agent-platform:outbox-signals")


def get_outbox_signal_block_ms() -> int:
    value = os.getenv("AGENT_PLATFORM_OUTBOX_SIGNAL_BLOCK_MS", "5000").strip()
    try:
        return max(1, int(value))
    except ValueError:
        return 5000


def get_outbox_signal_maxlen() -> int:
    value = os.getenv("AGENT_PLATFORM_OUTBOX_SIGNAL_MAXLEN", "10000").strip()
    try:
        return max(100, int(value))
    except ValueError:
        return 10000


def is_valid_database_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"postgres", "postgresql"} and bool(parsed.netloc)
