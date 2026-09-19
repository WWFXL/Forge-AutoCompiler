from __future__ import annotations

from pathlib import PurePosixPath


def artifact_display_path(path: object, source_path: object = None) -> str:
    """Return a stable artifact-relative path for user-facing evidence."""
    for candidate in (source_path, path):
        if not isinstance(candidate, str) or not candidate:
            continue
        normalized = candidate.replace("\\", "/")
        parts = PurePosixPath(normalized).parts
        try:
            marker = parts.index("artifacts")
        except ValueError:
            continue
        relative_parts = parts[marker + 1 :]
        if relative_parts and ".." not in relative_parts:
            return PurePosixPath(*relative_parts).as_posix()
    if isinstance(path, str) and path:
        return PurePosixPath(path.replace("\\", "/")).name
    return "artifact"
