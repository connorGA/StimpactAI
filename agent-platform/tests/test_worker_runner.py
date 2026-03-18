from __future__ import annotations

import pytest

from worker_runner import _worker_lock, _worker_lock_path


def test_worker_lock_rejects_second_same_worker_instance() -> None:
    worker_name = "autonomous-test"

    with _worker_lock(worker_name):
        with pytest.raises(SystemExit) as exc_info:
            with _worker_lock(worker_name):
                pass

    assert "already running" in str(exc_info.value)


def test_worker_lock_path_uses_temp_directory() -> None:
    path = _worker_lock_path("sandbox")

    assert path.name == "stimpact-sandbox.lock"
