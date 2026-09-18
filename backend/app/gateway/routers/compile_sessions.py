"""只读展示持久化编译证据，不参与编译生命周期。"""

import json
import os
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException

from deerflow.config.paths import get_paths

router = APIRouter(prefix="/api/threads/{thread_id}/compile-sessions", tags=["compile-sessions"])
MAX_METADATA_BYTES = 8 * 1024 * 1024
MAX_LOG_BYTES = 16 * 1024
_COMPONENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")


def _validate_id(value: str) -> None:
    if not _COMPONENT.fullmatch(value):
        raise HTTPException(400, "Invalid evidence identifier")


def _contained(path: Path, directory: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(directory) or resolved == directory:
        raise HTTPException(403, "Evidence path is outside the session")
    return resolved


def _redact(text: str) -> str:
    for name, value in os.environ.items():
        if len(value) >= 8 and re.search(r"API_KEY|TOKEN|SECRET|_AK$", name, re.IGNORECASE):
            text = text.replace(value, "[REDACTED]")
    text = re.sub(r"sk-[A-Za-z0-9_-]{8,}", "[REDACTED]", text)
    text = re.sub(r"(?i)(Bearer\s+)[A-Za-z0-9._~+/-]+", r"\1[REDACTED]", text)
    text = re.sub(r"(?i)([a-z][a-z0-9+.-]*://)[^/\s:@]+:[^/\s@]+@", r"\1[REDACTED]@", text)
    return re.sub(r"(?i)((?:api[_-]?key|token|password|secret)\s*[:=]\s*)[\"']?[^\s,\"']+", r"\1[REDACTED]", text)


def _fields(record: dict, names: tuple[str, ...]) -> dict:
    return {name: _redact(value) if isinstance(value := record.get(name), str) else value for name in names}


def _checks(record: dict) -> list[dict]:
    checks = record.get("checks", [])
    if not isinstance(checks, list):
        raise HTTPException(503, "Compile evidence is temporarily unavailable")
    return [_fields(check, ("name", "passed", "exit_code", "summary")) for check in checks if isinstance(check, dict)]


def _read_session(thread_id: str, session_id: str) -> tuple[Path, Path, dict]:
    _validate_id(thread_id)
    _validate_id(session_id)
    root = get_paths().compile_sessions_dir.resolve()
    directory = _contained(root / thread_id / session_id, root)
    metadata = _contained(directory / "session.json", directory)
    try:
        with metadata.open("rb") as stream:
            content = stream.read(MAX_METADATA_BYTES + 1)
        if len(content) > MAX_METADATA_BYTES:
            raise HTTPException(413, "Evidence metadata is too large")
        data = json.loads(content)
    except FileNotFoundError as exc:
        raise HTTPException(404, "Compile session not found") from exc
    except PermissionError as exc:
        raise HTTPException(403, "Compile evidence is not readable") from exc
    except (OSError, ValueError) as exc:
        raise HTTPException(503, "Compile evidence is temporarily unavailable") from exc
    if not isinstance(data, dict) or data.get("thread_id") != thread_id or data.get("session_id") != session_id:
        raise HTTPException(404, "Compile session not found")
    if not isinstance(data.get("commands", []), list) or not isinstance(data.get("replay_attempts", []), list):
        raise HTTPException(503, "Compile evidence is temporarily unavailable")
    return root, directory, data


@router.get("/{session_id}")
def get_compile_session(thread_id: str, session_id: str) -> dict:
    _, _, data = _read_session(thread_id, session_id)
    result = _fields(data, ("session_id", "status", "repo_url", "commit_sha", "selected_build_system", "executed_build_system"))
    result["commands"] = [
        {
            **_fields(command, ("command_id", "stage", "role", "command", "workdir", "exit_code", "duration_seconds", "timed_out")),
            "has_log": bool(command.get("log_path")),
        }
        for command in data.get("commands", [])
        if isinstance(command, dict)
    ]
    verification = data.get("verification")
    result["verification"] = {"status": verification.get("status"), "checks": _checks(verification)} if isinstance(verification, dict) else None
    result["replay_attempts"] = [
        {
            **_fields(attempt, ("attempt_id", "status", "duration_seconds", "failure_classification", "cleanup_succeeded")),
            "checks": _checks(attempt),
            "has_log": bool(attempt.get("log_path")),
        }
        for attempt in data.get("replay_attempts", [])
        if isinstance(attempt, dict)
    ]
    return result


def _read_log(thread_id: str, session_id: str, record_id: str, collection: str, id_field: str) -> dict:
    _validate_id(record_id)
    root, directory, data = _read_session(thread_id, session_id)
    record = next((item for item in data.get(collection, []) if isinstance(item, dict) and item.get(id_field) == record_id), None)
    if record is None or not isinstance(record.get("log_path"), str) or not record["log_path"]:
        raise HTTPException(404, "Evidence log not found")
    path = Path(record["log_path"])
    path = _contained(path if path.is_absolute() else root / path, directory)
    log_directory = directory / "logs" if collection == "commands" else directory / "replay" / record_id / "logs"
    path = _contained(path, log_directory)
    try:
        with path.open("rb") as stream:
            size = stream.seek(0, os.SEEK_END)
            stream.seek(max(0, size - MAX_LOG_BYTES))
            content = stream.read(MAX_LOG_BYTES)
    except FileNotFoundError as exc:
        raise HTTPException(404, "Evidence log not found") from exc
    except PermissionError as exc:
        raise HTTPException(403, "Evidence log is not readable") from exc
    except OSError as exc:
        raise HTTPException(503, "Evidence log is temporarily unavailable") from exc
    return {"output": _redact(content.decode("utf-8", errors="replace")), "truncated": size > MAX_LOG_BYTES}


@router.get("/{session_id}/commands/{command_id}/log")
def get_command_log(thread_id: str, session_id: str, command_id: str) -> dict:
    return _read_log(thread_id, session_id, command_id, "commands", "command_id")


@router.get("/{session_id}/replays/{attempt_id}/log")
def get_replay_log(thread_id: str, session_id: str, attempt_id: str) -> dict:
    return _read_log(thread_id, session_id, attempt_id, "replay_attempts", "attempt_id")
