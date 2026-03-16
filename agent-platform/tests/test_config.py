from __future__ import annotations

from api.core.config import (
    get_openai_chat_model,
    get_openai_model,
    get_openai_patch_model,
    get_openai_rca_model,
)


def clear_model_env(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_CHAT_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_RCA_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_PATCH_MODEL", raising=False)


def test_openai_model_defaults(monkeypatch) -> None:
    clear_model_env(monkeypatch)

    assert get_openai_model() == "gpt-4.1-mini"
    assert get_openai_chat_model() == "gpt-4.1-mini"
    assert get_openai_rca_model() == "gpt-4.1-mini"
    assert get_openai_patch_model() == "gpt-4.1-mini"


def test_chat_model_prefers_dedicated_override(monkeypatch) -> None:
    clear_model_env(monkeypatch)
    monkeypatch.setenv("OPENAI_MODEL", "shared-model")
    monkeypatch.setenv("OPENAI_CHAT_MODEL", "chat-model")

    assert get_openai_chat_model() == "chat-model"
    assert get_openai_rca_model() == "shared-model"


def test_rca_model_prefers_dedicated_override(monkeypatch) -> None:
    clear_model_env(monkeypatch)
    monkeypatch.setenv("OPENAI_MODEL", "shared-model")
    monkeypatch.setenv("OPENAI_RCA_MODEL", "rca-model")

    assert get_openai_rca_model() == "rca-model"
    assert get_openai_chat_model() == "shared-model"


def test_patch_model_falls_back_to_rca_then_shared(monkeypatch) -> None:
    clear_model_env(monkeypatch)
    monkeypatch.setenv("OPENAI_MODEL", "shared-model")
    monkeypatch.setenv("OPENAI_RCA_MODEL", "rca-model")

    assert get_openai_patch_model() == "rca-model"

    monkeypatch.setenv("OPENAI_PATCH_MODEL", "patch-model")
    assert get_openai_patch_model() == "patch-model"
