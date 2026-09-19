import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway.routers import compile_sessions as routes

BASE = "/api/threads/thread-1/compile-sessions/session-1"


@pytest.fixture
def evidence(tmp_path, monkeypatch):
    root = tmp_path / "sessions"
    directory = root / "thread-1" / "session-1"
    logs = directory / "logs"
    logs.mkdir(parents=True)
    log = logs / "build.log"
    log.write_text("build passed\n", encoding="utf-8")
    replay_log = directory / "replay" / "replay-1" / "logs" / "build.log"
    replay_log.parent.mkdir(parents=True)
    replay_log.write_text("replay failed\n", encoding="utf-8")
    verification_log = replay_log.with_name("verify.log")
    verification_log.write_text("verification failed\n", encoding="utf-8")
    data = {
        "thread_id": "thread-1",
        "session_id": "session-1",
        "status": "completed",
        "parallel_jobs": 4,
        "commands": [{"command_id": "command-1", "command": "cmake --build build", "exit_code": 0, "log_path": str(log)}],
        "verification": {"status": "passed", "checks": [{"name": "archive", "passed": True, "summary": "accepted"}]},
        "replay_attempts": [
            {
                "attempt_id": "replay-1",
                "status": "failed",
                "failure_classification": "verification_execution_failed",
                "checks": [{"name": "verification_execution", "passed": False}],
                "log_path": str(replay_log.relative_to(root)),
                "verification_log_path": str(verification_log.relative_to(root)),
                "verification_exit_code": 8,
            },
            {"attempt_id": "replay-2", "status": "passed", "cleanup_succeeded": True, "checks": []},
        ],
        "private": "not returned",
    }
    metadata = directory / "session.json"
    metadata.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(routes, "get_paths", lambda: SimpleNamespace(compile_sessions_dir=root))
    app = FastAPI()
    app.include_router(routes.router)
    with TestClient(app) as client:
        yield client, metadata, data, log


def _save(metadata, data):
    metadata.write_text(json.dumps(data), encoding="utf-8")


def test_snapshot_preserves_failed_and_successful_attempts_without_writes(evidence):
    client, metadata, _, log = evidence
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in metadata.parent.rglob("*") if p.is_file()}
    response = client.get(BASE)
    assert response.status_code == 200
    data = response.json()
    assert [a["status"] for a in data["replay_attempts"]] == ["failed", "passed"]
    assert data["parallel_jobs"] == 4
    assert data["commands"][0]["command"] == "cmake --build build"
    assert "private" not in data
    assert "log_path" not in data["commands"][0]
    assert client.get(BASE + "/commands/command-1/log").json() == {
        "output": log.read_bytes().decode("utf-8"),
        "truncated": False,
    }
    assert client.get(BASE + "/replays/replay-1/log").status_code == 200
    assert client.get(BASE + "/replays/replay-1/verification-log").json() == {
        "output": (metadata.parent / "replay" / "replay-1" / "logs" / "verify.log").read_bytes().decode("utf-8"),
        "truncated": False,
    }
    assert data["replay_attempts"][0]["has_verification_log"] is True
    assert data["replay_attempts"][0]["verification_exit_code"] == 8
    after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in metadata.parent.rglob("*") if p.is_file()}
    assert before == after


@pytest.mark.parametrize("parallel_jobs", [None, 0, -1, True, "8"])
def test_snapshot_defaults_invalid_or_missing_historical_parallel_policy(evidence, parallel_jobs):
    client, metadata, data, _ = evidence
    if parallel_jobs is None:
        data.pop("parallel_jobs")
    else:
        data["parallel_jobs"] = parallel_jobs
    _save(metadata, data)

    assert client.get(BASE).json()["parallel_jobs"] == 4


def test_bounded_tail_and_redaction(evidence, monkeypatch):
    client, metadata, data, log = evidence
    monkeypatch.setenv("DEEPSEEK_API_KEY", "private-provider-value")
    data["commands"][0]["command"] = "TOKEN=abcdefgh https://user:password@example.com sk-1234567890"
    _save(metadata, data)
    log.write_text("x" * (routes.MAX_LOG_BYTES + 10) + "\nBearer abcdefgh\nprivate-provider-value\n", encoding="utf-8")
    result = client.get(BASE + "/commands/command-1/log").json()
    assert result["truncated"] is True
    assert len(result["output"]) < routes.MAX_LOG_BYTES + 100
    assert "private-provider-value" not in result["output"]
    assert "abcdefgh" not in result["output"]
    command = client.get(BASE).json()["commands"][0]["command"]
    assert "password" not in command
    assert "sk-1234567890" not in command
    assert "abcdefgh" not in command


@pytest.mark.parametrize("field", ["thread_id", "session_id"])
def test_metadata_identity_must_match_url(evidence, field):
    client, metadata, data, _ = evidence
    data[field] = "other"
    _save(metadata, data)
    assert client.get(BASE).status_code == 404


@pytest.mark.parametrize("value", ["{", "[]", '{"commands":null,"thread_id":"thread-1","session_id":"session-1"}'])
def test_unavailable_metadata_is_not_reported_as_success(evidence, value):
    client, metadata, _, _ = evidence
    metadata.write_text(value, encoding="utf-8")
    assert client.get(BASE).status_code in {404, 503}


def test_missing_and_oversized_metadata(evidence, monkeypatch):
    client, metadata, _, _ = evidence
    monkeypatch.setattr(routes, "MAX_METADATA_BYTES", 8)
    assert client.get(BASE).status_code == 413
    metadata.unlink()
    assert client.get(BASE).status_code == 404


@pytest.mark.parametrize("suffix", ["/commands/unknown/log", "/replays/unknown/log", "/commands/bad%3Aid/log"])
def test_unknown_or_invalid_record_is_rejected(evidence, suffix):
    client, _, _, _ = evidence
    assert client.get(BASE + suffix).status_code in {400, 404}


def test_external_and_cross_thread_log_paths_are_rejected(evidence, tmp_path):
    client, metadata, data, _ = evidence
    outside = tmp_path / "private.txt"
    outside.write_text("secret", encoding="utf-8")
    for path in (str(outside), "thread-2/session-2/logs/private.txt", "../private.txt"):
        data["commands"][0]["log_path"] = path
        _save(metadata, data)
        assert client.get(BASE + "/commands/command-1/log").status_code == 403


def test_log_symlink_escape_is_rejected(evidence, tmp_path):
    client, metadata, data, log = evidence
    outside = tmp_path / "private.txt"
    outside.write_text("secret", encoding="utf-8")
    link = log.parent / "link.log"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("当前系统不允许创建符号链接")
    data["commands"][0]["log_path"] = str(link)
    _save(metadata, data)
    assert client.get(BASE + "/commands/command-1/log").status_code == 403


def test_permission_error_has_safe_response(evidence, monkeypatch):
    client, metadata, _, _ = evidence
    original = Path.open

    def denied(path, *args, **kwargs):
        if path == metadata:
            raise PermissionError("private absolute path")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", denied)
    response = client.get(BASE)
    assert response.status_code == 403
    assert "private absolute path" not in response.text


@pytest.mark.parametrize("collection", ["verification", "replay_attempts"])
def test_invalid_checks_return_safe_error(evidence, collection):
    client, metadata, data, _ = evidence
    record = data[collection] if collection == "verification" else data[collection][0]
    record["checks"] = None
    _save(metadata, data)
    assert client.get(BASE).status_code == 503


def test_non_log_session_file_is_rejected(evidence):
    client, metadata, data, _ = evidence
    data["commands"][0]["log_path"] = str(metadata)
    _save(metadata, data)
    assert client.get(BASE + "/commands/command-1/log").status_code == 403


def test_missing_log_is_explicit(evidence):
    client, _, _, log = evidence
    log.unlink()
    assert client.get(BASE + "/commands/command-1/log").status_code == 404


def test_metadata_symlink_escape_is_rejected(evidence, tmp_path):
    client, metadata, data, _ = evidence
    outside = tmp_path / "private.json"
    outside.write_text(json.dumps(data), encoding="utf-8")
    metadata.unlink()
    try:
        metadata.symlink_to(outside)
    except OSError:
        pytest.skip("creating symlinks requires additional privileges on this platform")
    assert client.get(BASE).status_code == 403
