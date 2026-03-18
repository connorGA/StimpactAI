from __future__ import annotations

from pathlib import Path

from staging_drill import _seed_drill_fixture


def test_seed_drill_fixture_writes_expected_buggy_retry_files(tmp_path: Path) -> None:
    fixture_dir = tmp_path / "staging_drill_fixture"
    fixture_dir.mkdir()
    (fixture_dir / "buggy_retry.py").write_text("print('stale')\n", encoding="utf-8")

    scenario = _seed_drill_fixture(str(tmp_path))

    assert scenario.name == "header-key"
    assert (fixture_dir / "__init__.py").read_text(encoding="utf-8") == ""
    assert (fixture_dir / "buggy_retry.py").read_text(encoding="utf-8") == (
        "def read_retry_after(headers: dict[str, str]) -> int:\n"
        "    value = headers[\"retry_after_seconds\"]\n"
        "    return int(value)\n"
    )
    assert (fixture_dir / "test_buggy_retry.py").read_text(encoding="utf-8") == (
        "from staging_drill_fixture.buggy_retry import read_retry_after\n\n\n"
        "def test_read_retry_after_uses_standard_header() -> None:\n"
        "    headers = {\"Retry-After\": \"7\"}\n"
        "    assert read_retry_after(headers) == 7\n"
    )


def test_seed_drill_fixture_supports_alternate_parse_digit_scenario(tmp_path: Path) -> None:
    fixture_dir = tmp_path / "staging_drill_fixture"
    fixture_dir.mkdir()

    scenario = _seed_drill_fixture(str(tmp_path), scenario_name="parse-digit")

    assert scenario.name == "parse-digit"
    assert (fixture_dir / "buggy_retry.py").read_text(encoding="utf-8") == (
        "def parse_retry_after(value: str) -> int:\n"
        "    return int(value[1:])\n"
    )
    assert (fixture_dir / "test_buggy_retry.py").read_text(encoding="utf-8") == (
        "from staging_drill_fixture.buggy_retry import parse_retry_after\n\n\n"
        "def test_parse_retry_after_keeps_the_full_number() -> None:\n"
        "    assert parse_retry_after(\"15\") == 15\n"
    )
