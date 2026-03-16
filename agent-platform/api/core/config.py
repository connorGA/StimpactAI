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


def _get_model_from_env(*names: str, default: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value is None:
            continue
        normalized = value.strip()
        if normalized:
            return normalized
    return default


def get_openai_model() -> str:
    return _get_model_from_env("OPENAI_MODEL", default="gpt-4.1-mini")


def get_openai_chat_model() -> str:
    return _get_model_from_env(
        "OPENAI_CHAT_MODEL",
        "OPENAI_MODEL",
        default="gpt-4.1-mini",
    )


def get_openai_rca_model() -> str:
    return _get_model_from_env(
        "OPENAI_RCA_MODEL",
        "OPENAI_MODEL",
        default="gpt-4.1-mini",
    )


def get_openai_patch_model() -> str:
    return _get_model_from_env(
        "OPENAI_PATCH_MODEL",
        "OPENAI_RCA_MODEL",
        "OPENAI_MODEL",
        default="gpt-4.1-mini",
    )


def get_repository_root() -> Path:
    value = os.getenv("AGENT_PLATFORM_REPOSITORY_ROOT")
    if value is None or not value.strip():
        return REPO_ROOT

    candidate = Path(value.strip()).expanduser()
    if not candidate.is_absolute():
        candidate = (REPO_ROOT / candidate).resolve()
    return candidate


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
