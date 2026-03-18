from staging_drill_fixture.buggy_retry import read_retry_after


def test_read_retry_after_uses_standard_header() -> None:
    headers = {"Retry-After": "7"}
    assert read_retry_after(headers) == 7
