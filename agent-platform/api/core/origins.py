from __future__ import annotations

from urllib.parse import urlparse


def normalize_origin(value: str | None) -> str | None:
    if value is None:
        return None
    parsed = urlparse(value.strip())
    if not parsed.scheme or not parsed.netloc:
        return None
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        return None
    return f"{scheme}://{parsed.netloc.lower()}".rstrip("/")


def normalize_origin_list(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        origin = normalize_origin(value)
        if origin is None or origin in seen:
            continue
        seen.add(origin)
        normalized.append(origin)
    return normalized
