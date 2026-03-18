def read_retry_after(headers: dict[str, str]) -> int:
    value = headers["retry_after_seconds"]
    return int(value)
