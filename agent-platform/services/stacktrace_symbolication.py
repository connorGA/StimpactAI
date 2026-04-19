from __future__ import annotations

import json
import re

from api.repositories.artifact_repository import ArtifactRepository
from api.repositories.release_sourcemap_repository import ReleaseSourcemapRepository
from services.artifact_storage import ArtifactStorage

_STACK_FRAME_RE = re.compile(r"(?P<bundle>https?://\S+|/\S+):(?P<line>\d+):(?P<column>\d+)")


class StacktraceSymbolicationService:
    def __init__(
        self,
        *,
        sourcemap_repository: ReleaseSourcemapRepository,
        artifact_repository: ArtifactRepository,
        artifact_storage: ArtifactStorage,
    ) -> None:
        self._sourcemap_repository = sourcemap_repository
        self._artifact_repository = artifact_repository
        self._artifact_storage = artifact_storage

    async def symbolicate(
        self,
        *,
        project_id: str,
        release: str | None,
        dist: str | None,
        stacktrace: str,
    ) -> str | None:
        if not release:
            return None
        output_lines: list[str] = []
        changed = False
        for raw_line in stacktrace.splitlines():
            match = _STACK_FRAME_RE.search(raw_line)
            if match is None:
                output_lines.append(raw_line)
                continue
            bundle_path = match.group("bundle")
            resolved = await self._resolve_frame(
                project_id=project_id,
                release=release,
                dist=dist or "",
                bundle_path=bundle_path,
                line=int(match.group("line")),
                column=int(match.group("column")),
            )
            if resolved is None:
                output_lines.append(raw_line)
                continue
            changed = True
            output_lines.append(
                f"{raw_line} -> {resolved['source']}:{resolved['line']}:{resolved['column']}"
            )
        if not changed:
            return None
        return "\n".join(output_lines)

    async def _resolve_frame(
        self,
        *,
        project_id: str,
        release: str,
        dist: str,
        bundle_path: str,
        line: int,
        column: int,
    ) -> dict[str, object] | None:
        record = await self._sourcemap_repository.get_release_sourcemap(
            project_id=project_id,
            release=release,
            dist=dist,
            bundle_path=bundle_path,
        )
        if record is None:
            return None
        artifact = await self._artifact_repository.get_artifact(record.artifact_id)
        if artifact is None:
            return None
        try:
            raw_bytes = self._artifact_storage.get_bytes(object_key=artifact.object_key)
            raw_text = raw_bytes.decode("utf-8")
            import sourcemap  # type: ignore

            index = sourcemap.loads(raw_text)
            token = index.lookup(line - 1, column - 1)
        except Exception:
            return None
        if token is None:
            return None
        return {
            "source": getattr(token, "src", None) or getattr(token, "source", None) or bundle_path,
            "line": int(getattr(token, "src_line", 0)) + 1,
            "column": int(getattr(token, "src_col", 0)) + 1,
            "name": getattr(token, "name", None),
        }


def build_sourcemap_object_key(*, project_id: str, release: str, dist: str, bundle_path: str) -> str:
    normalized_bundle = re.sub(r"[^a-zA-Z0-9._/-]+", "_", bundle_path.strip("/")) or "bundle"
    normalized_dist = dist or "default"
    return f"releases/{project_id}/{release}/{normalized_dist}/{normalized_bundle}.map"


def build_sourcemap_payload(*, bundle_path: str, sourcemap_text: str) -> dict[str, object]:
    parsed: dict[str, object]
    try:
        parsed = json.loads(sourcemap_text)
    except json.JSONDecodeError:
        parsed = {}
    return {
        "bundle_path": bundle_path,
        "version": parsed.get("version"),
        "file": parsed.get("file"),
        "sources": parsed.get("sources", []),
    }
