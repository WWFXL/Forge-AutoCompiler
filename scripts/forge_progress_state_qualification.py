#!/usr/bin/env python3
"""Issue #382 跨构建系统进展状态的只读离线资格审计。"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent
DEFAULT_SESSIONS_ROOT = REPO_ROOT / ".compile-sessions"
DEFAULT_MANIFEST = (
    REPO_ROOT
    / "benchmarks"
    / "manifests"
    / "cpp-cross-build-progress-state-qualification-v1.json"
)
DEFAULT_MANUAL_AUDIT = (
    REPO_ROOT
    / "benchmarks"
    / "fixtures"
    / "cpp-cross-build-progress-state-manual-audit-v1.json"
)
DEFAULT_JSON_REPORT = (
    REPO_ROOT
    / "benchmarks"
    / "reports"
    / "cpp-cross-build-progress-state-qualification-v1.json"
)
DEFAULT_MARKDOWN_REPORT = (
    REPO_ROOT
    / "benchmarks"
    / "reports"
    / "cpp-cross-build-progress-state-qualification-v1.md"
)
PREREGISTRATION = (
    REPO_ROOT
    / "benchmarks"
    / "preregistrations"
    / "cpp-cross-build-progress-state-qualification-v1.md"
)

IDENTITY = "cpp-cross-build-progress-state-qualification-v1"
ISSUE_URL = "https://github.com/WWFXL/Forge-AutoCompiler/issues/382"
MANIFEST_SCHEMA = "forge-cross-build-progress-state-input-manifest-1.0.0"
MANUAL_SCHEMA = "forge-cross-build-progress-state-manual-audit-1.0.0"
REPORT_SCHEMA = "forge-cross-build-progress-state-qualification-report-1.0.0"

BUILD_SYSTEMS = ("cmake", "make", "autotools")
ELIGIBLE_ROLES = (
    "dependency",
    "configure",
    "build",
    "diagnostic",
    "smoke",
    "artifact_stage",
)
OBLIGATIONS = (
    "source_available",
    "toolchain_ready",
    "configuration_generated",
    "build_graph_ready",
    "contract_target_built",
    "artifacts_staged",
    "functional_oracle_passed",
    "provenance_verified",
    "clean_replay_closed",
)
OBLIGATION_STATUSES = ("pending", "verified", "invalidated", "not_applicable")
TRANSITIONS = ("progress", "lateral", "stagnation", "regression")
DIAGNOSTIC_CATEGORIES = (
    "none",
    "timeout",
    "policy_rejected",
    "dependency_missing",
    "configuration_error",
    "compile_error",
    "link_error",
    "target_error",
    "artifact_error",
    "test_error",
    "unknown_error",
)
SESSION_KEYS = ("repo_url", "commit_sha", "build_system", "created_at", "commands")
COMMAND_KEYS = (
    "command_id",
    "role",
    "timeout_seconds",
    "duration_seconds",
    "timed_out",
    "termination",
    "started_at",
    "completed_at",
    "exit_code",
    "log_path",
)
EXACT_COMMIT_RE = re.compile(r"^[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?$")
STAGE_C_ATTEMPT_RE = re.compile(r"^stage-c-v5-.+-r[12]-b$")
MAX_DIAGNOSTIC_BYTES = 131_072
BOOTSTRAP_SAMPLES = 10_000
RANDOM_SEED = 382

NUMERIC_FEATURES = {
    "budget": [
        "turn_index",
        "commands_used",
        "wall_clock_seconds_used",
        "model_requests_used",
        "recorded_tokens_used",
    ],
    "context": [],
    "error": [],
    "simple_combined": [
        "turn_index",
        "commands_used",
        "wall_clock_seconds_used",
        "model_requests_used",
        "recorded_tokens_used",
    ],
    "progress_state": [
        "turn_index",
        "commands_used",
        "wall_clock_seconds_used",
        "model_requests_used",
        "recorded_tokens_used",
        "verified_count",
        "invalidated_count",
        "state_repeat_count",
    ],
}
CATEGORICAL_FEATURES = {
    "budget": ["next_action_role"],
    "context": ["build_system", "next_action_role"],
    "error": ["next_action_role", "prior_error_category"],
    "simple_combined": [
        "build_system",
        "next_action_role",
        "prior_error_category",
    ],
    "progress_state": [
        "build_system",
        "next_action_role",
        "prior_error_category",
        "frontier_obligation",
        "previous_transition",
        *(f"obligation_{name}" for name in OBLIGATIONS),
    ],
}


class QualificationError(RuntimeError):
    """资格审计输入或不变量不满足预注册。"""


@dataclass(frozen=True)
class ProgressState:
    obligations: dict[str, str]
    diagnostic_category: str


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise QualificationError(f"无法读取 {label}: {path}") from exc
    if not isinstance(value, dict):
        raise QualificationError(f"{label} 顶层必须为对象: {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def normalize_project_family(repo_url: str) -> str:
    parsed = urlparse(repo_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise QualificationError(f"不支持的 repo_url: {repo_url!r}")
    path = parsed.path.strip("/")
    if path.lower().endswith(".git"):
        path = path[:-4]
    parts = [part for part in path.split("/") if part]
    if len(parts) != 2:
        raise QualificationError(f"repo_url 不是 owner/repo: {repo_url!r}")
    return f"{parsed.hostname.lower()}/{parts[0].lower()}/{parts[1].lower()}"


def _read_allowed_session(path: Path) -> dict[str, Any]:
    raw = load_json(path, "session")
    commands = raw.get("commands")
    if not isinstance(commands, list):
        raise QualificationError(f"session.commands 必须为数组: {path}")
    allowed_commands: list[dict[str, Any]] = []
    for index, command in enumerate(commands):
        if not isinstance(command, dict):
            raise QualificationError(f"session command #{index} 必须为对象: {path}")
        allowed_commands.append({key: command.get(key) for key in COMMAND_KEYS})
    return {
        key: allowed_commands if key == "commands" else raw.get(key)
        for key in SESSION_KEYS
    }


def _parse_timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise QualificationError(f"{label} 缺少 ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise QualificationError(f"{label} timestamp 非法: {value!r}") from exc
    if parsed.tzinfo is None:
        raise QualificationError(f"{label} timestamp 必须包含时区: {value!r}")
    return parsed


def _relative_source_path(path: Path, sessions_root: Path) -> str:
    try:
        return path.resolve().relative_to(sessions_root.resolve()).as_posix()
    except ValueError as exc:
        raise QualificationError(f"证据路径越出 sessions root: {path}") from exc


def resolve_evidence_path(
    session_path: Path,
    raw_path: Any,
    sessions_root: Path,
) -> Path:
    if not isinstance(raw_path, str) or not raw_path:
        raise QualificationError(f"command.log_path 缺失: {session_path}")
    normalized = raw_path.replace("\\", "/")
    marker = ".compile-sessions/"
    candidates: list[Path] = []
    if marker in normalized:
        candidates.append(sessions_root / normalized.split(marker, 1)[1])
    candidates.append(session_path.parent / "logs" / Path(normalized).name)
    root = sessions_root.resolve()
    for candidate in candidates:
        resolved = candidate.resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            continue
        if resolved.is_file():
            return resolved
    raise QualificationError(
        f"无法在只读 sessions root 内解析命令日志: {session_path} -> {raw_path}"
    )


def _event_log_for_session(
    session_path: Path,
    *,
    expected_attempt: re.Pattern[str] | None = None,
) -> tuple[str, Path]:
    workflow_root = session_path.parent / "agent-workflow"
    candidates = sorted(workflow_root.glob("*/events.jsonl"))
    if expected_attempt is not None:
        candidates = [
            path for path in candidates if expected_attempt.fullmatch(path.parent.name)
        ]
    if len(candidates) != 1:
        raise QualificationError(
            f"session 必须恰有一个匹配的 agent-workflow ledger: {session_path}"
        )
    return candidates[0].parent.name, candidates[0]


def _manifest_record(
    session_path: Path,
    sessions_root: Path,
    split: str,
    attempt_id: str,
    event_log: Path,
) -> dict[str, Any]:
    session = _read_allowed_session(session_path)
    repo_url = session.get("repo_url")
    build_system = session.get("build_system")
    created_at = session.get("created_at")
    commit_sha = session.get("commit_sha")
    if not isinstance(repo_url, str):
        raise QualificationError(f"session.repo_url 缺失: {session_path}")
    if build_system not in BUILD_SYSTEMS:
        raise QualificationError(f"build_system 不在冻结集合: {session_path}")
    _parse_timestamp(created_at, "session.created_at")
    if not isinstance(commit_sha, str) or not EXACT_COMMIT_RE.fullmatch(commit_sha):
        raise QualificationError(f"session 缺少 exact commit: {session_path}")

    command_logs: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for command in session["commands"]:
        command_id = command.get("command_id")
        if not isinstance(command_id, str) or not command_id:
            raise QualificationError(f"command_id 缺失: {session_path}")
        if command_id in seen_ids:
            raise QualificationError(f"command_id 重复: {session_path} {command_id}")
        seen_ids.add(command_id)
        log_path = resolve_evidence_path(
            session_path,
            command.get("log_path"),
            sessions_root,
        )
        command_logs.append(
            {
                "command_id": command_id,
                "path": _relative_source_path(log_path, sessions_root),
                "sha256": file_sha256(log_path),
                "size_bytes": log_path.stat().st_size,
            }
        )

    record = {
        "split": split,
        "session_path": _relative_source_path(session_path, sessions_root),
        "session_sha256": file_sha256(session_path),
        "project_family": normalize_project_family(repo_url),
        "repo_url": repo_url,
        "commit_sha": commit_sha.lower(),
        "build_system": build_system,
        "created_at": created_at,
        "attempt_id": attempt_id,
        "event_log": {
            "path": _relative_source_path(event_log, sessions_root),
            "sha256": file_sha256(event_log),
            "size_bytes": event_log.stat().st_size,
        },
        "command_count": len(session["commands"]),
        "eligible_command_count": sum(
            command.get("role") in ELIGIBLE_ROLES for command in session["commands"]
        ),
        "command_logs": command_logs,
        "command_log_bundle_sha256": canonical_sha256(command_logs),
    }
    if record["eligible_command_count"] < 1:
        raise QualificationError(f"session 没有 eligible command: {session_path}")
    return record


def generate_input_manifest(
    sessions_root: Path = DEFAULT_SESSIONS_ROOT,
) -> dict[str, Any]:
    sessions_root = sessions_root.resolve()
    development_paths = sorted(
        sessions_root.glob("phase5-v3-*-191062f15d83/*/session.json")
    )
    development: list[dict[str, Any]] = []
    for path in development_paths:
        attempt_id, event_log = _event_log_for_session(path)
        development.append(
            _manifest_record(path, sessions_root, "development", attempt_id, event_log)
        )

    evaluation: list[dict[str, Any]] = []
    for path in sorted(sessions_root.glob("stage-c-b-*/*/session.json")):
        try:
            attempt_id, event_log = _event_log_for_session(
                path,
                expected_attempt=STAGE_C_ATTEMPT_RE,
            )
        except QualificationError:
            continue
        evaluation.append(
            _manifest_record(path, sessions_root, "evaluation", attempt_id, event_log)
        )

    development.sort(key=lambda item: item["project_family"])
    evaluation.sort(key=lambda item: (item["project_family"], item["attempt_id"]))
    if len(development) != 6:
        raise QualificationError(
            f"开发集必须恰有 6 个 session，实际 {len(development)}"
        )
    if len(evaluation) != 24:
        raise QualificationError(
            f"隔离测试集必须恰有 24 个 session，实际 {len(evaluation)}"
        )

    development_families = {item["project_family"] for item in development}
    evaluation_counts = Counter(item["project_family"] for item in evaluation)
    evaluation_families = set(evaluation_counts)
    if len(development_families) != 6:
        raise QualificationError("开发集项目族必须恰有 6 个")
    if len(evaluation_families) != 12 or set(evaluation_counts.values()) != {2}:
        raise QualificationError("隔离测试集必须为 12 个项目族且每族恰有 2 个重复")
    overlap = development_families & evaluation_families
    if overlap:
        raise QualificationError(f"开发/测试项目族重合: {sorted(overlap)}")

    development_latest = max(
        _parse_timestamp(item["created_at"], "development.created_at")
        for item in development
    )
    evaluation_earliest = min(
        _parse_timestamp(item["created_at"], "evaluation.created_at")
        for item in evaluation
    )
    if not development_latest < evaluation_earliest:
        raise QualificationError("开发/测试时间没有严格前后分离")

    evaluation_system_families = {
        system: len(
            {
                item["project_family"]
                for item in evaluation
                if item["build_system"] == system
            }
        )
        for system in BUILD_SYSTEMS
    }
    if any(value < 3 for value in evaluation_system_families.values()):
        raise QualificationError(
            f"隔离测试集构建系统项目族覆盖不足: {evaluation_system_families}"
        )

    inputs = [*development, *evaluation]
    return {
        "schema_version": MANIFEST_SCHEMA,
        "identity": IDENTITY,
        "issue": ISSUE_URL,
        "source_root": ".compile-sessions",
        "selection": {
            "development": "phase5-v3-*-191062f15d83/*/session.json",
            "evaluation_session_root": "stage-c-b-*/*/session.json",
            "evaluation_attempt_regex": STAGE_C_ATTEMPT_RE.pattern,
            "excluded_session_count_observed_during_inventory": 139,
            "unreadable_session_count_observed_during_inventory": 13,
        },
        "summary": {
            "session_count": len(inputs),
            "development_session_count": len(development),
            "evaluation_session_count": len(evaluation),
            "development_project_family_count": len(development_families),
            "evaluation_project_family_count": len(evaluation_families),
            "development_latest_created_at": development_latest.isoformat(),
            "evaluation_earliest_created_at": evaluation_earliest.isoformat(),
            "evaluation_project_families_by_build_system": evaluation_system_families,
            "command_count": sum(item["command_count"] for item in inputs),
            "eligible_command_count": sum(
                item["eligible_command_count"] for item in inputs
            ),
        },
        "inputs": inputs,
    }


def verify_input_manifest(
    manifest: dict[str, Any],
    sessions_root: Path = DEFAULT_SESSIONS_ROOT,
) -> dict[str, Any]:
    if manifest.get("schema_version") != MANIFEST_SCHEMA:
        raise QualificationError("输入清单 schema_version 不匹配")
    regenerated = generate_input_manifest(sessions_root)
    if regenerated != manifest:
        raise QualificationError("只读输入清单与当前证据路径或哈希不一致")
    return {
        "manifest_sha256": canonical_sha256(manifest),
        **manifest["summary"],
        "verified": True,
    }


def _diagnostic_text(path: Path) -> str:
    size = path.stat().st_size
    with path.open("rb") as stream:
        if size <= MAX_DIAGNOSTIC_BYTES:
            payload = stream.read()
        else:
            half = MAX_DIAGNOSTIC_BYTES // 2
            prefix = stream.read(half)
            stream.seek(max(0, size - half))
            suffix = stream.read(half)
            payload = prefix + b"\n[...truncated...]\n" + suffix
    return payload.decode("utf-8", errors="replace").lower()


def classify_diagnostic(command: dict[str, Any], log_text: str) -> str:
    exit_code = command.get("exit_code")
    termination = str(command.get("termination") or "").lower()
    role = command.get("role")
    if exit_code == 0 and not command.get("timed_out"):
        return "none"
    if command.get("timed_out") or "timeout" in termination:
        return "timeout"
    if (
        "policy_rejected" in termination
        or "policy rejected" in log_text
        or "policy_rejected" in log_text
        or "command rejected" in log_text
    ):
        return "policy_rejected"

    patterns: tuple[tuple[str, tuple[str, ...]], ...] = (
        (
            "dependency_missing",
            (
                "command not found",
                "package not found",
                "could not find package",
                "no package '",
                "fatal error:",
                "no such file or directory",
                "cannot find -l",
                "missing dependency",
                "dependency not found",
            ),
        ),
        (
            "configuration_error",
            (
                "cmake error",
                "configure: error",
                "configuration failed",
                "autoreconf: error",
                "config.status: error",
            ),
        ),
        (
            "compile_error",
            (
                "compilation terminated",
                "internal compiler error",
                " error:",
                "ninja: build stopped",
            ),
        ),
        (
            "link_error",
            (
                "undefined reference",
                "linker command failed",
                "ld returned",
                "cannot find -l",
            ),
        ),
        (
            "target_error",
            (
                "no rule to make target",
                "unknown target",
                "target mapping",
                "target not found",
            ),
        ),
        (
            "artifact_error",
            (
                "cannot stat",
                "no compiled artifact",
                "artifact not found",
                "not a regular file",
                "cp: cannot",
            ),
        ),
        (
            "test_error",
            (
                "test failed",
                "tests failed",
                "assertion failed",
                "segmentation fault",
                "smoke test",
            ),
        ),
    )
    for category, needles in patterns:
        if any(needle in log_text for needle in needles):
            return category

    fallback = {
        "dependency": "dependency_missing",
        "configure": "configuration_error",
        "build": "compile_error",
        "artifact_stage": "artifact_error",
        "smoke": "test_error",
    }
    return fallback.get(role, "unknown_error")


def initial_state(build_system: str, commit_sha: str | None) -> ProgressState:
    if build_system not in BUILD_SYSTEMS:
        raise QualificationError(f"不支持的构建系统: {build_system!r}")
    obligations = {name: "pending" for name in OBLIGATIONS}
    if isinstance(commit_sha, str) and EXACT_COMMIT_RE.fullmatch(commit_sha):
        obligations["source_available"] = "verified"
    if build_system == "make":
        obligations["configuration_generated"] = "not_applicable"
    return ProgressState(obligations=obligations, diagnostic_category="none")


def _invalidate(obligations: dict[str, str], names: Iterable[str]) -> None:
    for name in names:
        if obligations[name] == "verified":
            obligations[name] = "invalidated"


def apply_command(
    state: ProgressState,
    command: dict[str, Any],
    log_text: str,
) -> ProgressState:
    role = command.get("role")
    if role not in ELIGIBLE_ROLES:
        raise QualificationError(f"不支持的 command role: {role!r}")
    diagnostic = classify_diagnostic(command, log_text)
    obligations = copy.deepcopy(state.obligations)
    executed = diagnostic != "policy_rejected"
    succeeded = (
        executed
        and command.get("exit_code") == 0
        and not bool(command.get("timed_out"))
    )

    if role == "dependency" and succeeded:
        _invalidate(obligations, OBLIGATIONS[2:])
        obligations["toolchain_ready"] = "verified"
    elif role == "configure" and executed:
        _invalidate(obligations, OBLIGATIONS[2:])
        if succeeded:
            obligations["toolchain_ready"] = "verified"
            if obligations["configuration_generated"] != "not_applicable":
                obligations["configuration_generated"] = "verified"
            obligations["build_graph_ready"] = "verified"
    elif role == "build" and executed:
        _invalidate(obligations, OBLIGATIONS[4:])
        if succeeded:
            obligations["toolchain_ready"] = "verified"
            if obligations["configuration_generated"] != "not_applicable":
                obligations["configuration_generated"] = "verified"
            obligations["build_graph_ready"] = "verified"
            obligations["contract_target_built"] = "verified"
    elif role == "artifact_stage" and executed:
        _invalidate(obligations, OBLIGATIONS[5:])
        if succeeded:
            obligations["artifacts_staged"] = "verified"
    elif role == "smoke" and executed:
        _invalidate(obligations, OBLIGATIONS[6:])
        if succeeded:
            obligations["functional_oracle_passed"] = "verified"

    if any(value not in OBLIGATION_STATUSES for value in obligations.values()):
        raise QualificationError("extractor 生成了非法 obligation status")
    return ProgressState(
        obligations=obligations,
        diagnostic_category=diagnostic,
    )


def classify_transition(before: ProgressState, after: ProgressState) -> str:
    regressed = any(
        before.obligations[name] == "verified" and after.obligations[name] != "verified"
        for name in OBLIGATIONS
    )
    if regressed:
        return "regression"
    progressed = any(
        before.obligations[name] != "verified" and after.obligations[name] == "verified"
        for name in OBLIGATIONS
    )
    if progressed:
        return "progress"
    if (
        before.obligations == after.obligations
        and before.diagnostic_category == after.diagnostic_category
    ):
        return "stagnation"
    return "lateral"


def state_signature(state: ProgressState) -> str:
    return canonical_sha256(
        {
            "obligations": state.obligations,
            "diagnostic_category": state.diagnostic_category,
        }
    )


def frontier_obligation(state: ProgressState) -> str:
    for desired in ("invalidated", "pending"):
        for name in OBLIGATIONS:
            if state.obligations[name] == desired:
                return name
    return "complete"


def _load_token_events(path: Path) -> list[tuple[datetime, int]]:
    events: list[tuple[datetime, int]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise QualificationError(f"无法读取 token ledger: {path}") from exc
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise QualificationError(
                f"token ledger 第 {line_number} 行不是 JSON: {path}"
            ) from exc
        if (
            not isinstance(event, dict)
            or event.get("event_type") != "model.request_completed"
        ):
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict):
            raise QualificationError(f"model.request_completed payload 非对象: {path}")
        recorded_tokens = payload.get("recorded_tokens")
        request_sequence = payload.get("request_sequence")
        if (
            not isinstance(recorded_tokens, int)
            or isinstance(recorded_tokens, bool)
            or recorded_tokens < 0
        ):
            raise QualificationError(f"recorded_tokens 非法: {path}")
        if (
            not isinstance(request_sequence, int)
            or isinstance(request_sequence, bool)
            or request_sequence < 1
        ):
            raise QualificationError(f"request_sequence 非法: {path}")
        timestamp = _parse_timestamp(event.get("timestamp"), "model request")
        events.append((timestamp, recorded_tokens))
    events.sort(key=lambda item: item[0])
    return events


def _budget_before(
    events: list[tuple[datetime, int]],
    command_started_at: datetime,
) -> tuple[int, int]:
    used = [tokens for timestamp, tokens in events if timestamp <= command_started_at]
    return len(used), sum(used)


def _manifest_log_map(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    logs = record.get("command_logs")
    if not isinstance(logs, list):
        raise QualificationError("manifest command_logs 必须为数组")
    mapping = {item.get("command_id"): item for item in logs if isinstance(item, dict)}
    if len(mapping) != len(logs):
        raise QualificationError("manifest command_logs 存在重复或无效 command_id")
    return mapping


def extract_rows_for_record(
    record: dict[str, Any],
    sessions_root: Path,
) -> list[dict[str, Any]]:
    session_path = sessions_root / record["session_path"]
    session = _read_allowed_session(session_path)
    event_path = sessions_root / record["event_log"]["path"]
    token_events = _load_token_events(event_path)
    log_map = _manifest_log_map(record)

    state = initial_state(record["build_system"], record["commit_sha"])
    previous_transition = "none"
    seen_signatures: Counter[str] = Counter()
    duration_used = 0.0
    rows: list[dict[str, Any]] = []
    turn_index = 0
    for command in session["commands"]:
        role = command.get("role")
        if role not in ELIGIBLE_ROLES:
            continue
        turn_index += 1
        command_id = command.get("command_id")
        log_ref = log_map.get(command_id)
        if not isinstance(log_ref, dict):
            raise QualificationError(f"manifest 缺少 command log: {command_id}")
        log_path = sessions_root / log_ref["path"]
        started_at = _parse_timestamp(command.get("started_at"), "command.started_at")
        requests_used, tokens_used = _budget_before(token_events, started_at)

        before = state
        signature = state_signature(before)
        repeat_count = seen_signatures[signature]
        seen_signatures[signature] += 1
        after = apply_command(before, command, _diagnostic_text(log_path))
        transition = classify_transition(before, after)
        if transition not in TRANSITIONS:
            raise QualificationError(f"非法 transition: {transition}")

        row: dict[str, Any] = {
            "split": record["split"],
            "session_path": record["session_path"],
            "attempt_id": record["attempt_id"],
            "project_family": record["project_family"],
            "build_system": record["build_system"],
            "command_id": command_id,
            "turn_index": turn_index,
            "commands_used": turn_index - 1,
            "wall_clock_seconds_used": round(duration_used, 9),
            "model_requests_used": requests_used,
            "recorded_tokens_used": tokens_used,
            "next_action_role": role,
            "prior_error_category": before.diagnostic_category,
            "frontier_obligation": frontier_obligation(before),
            "verified_count": sum(
                value == "verified" for value in before.obligations.values()
            ),
            "invalidated_count": sum(
                value == "invalidated" for value in before.obligations.values()
            ),
            "previous_transition": previous_transition,
            "state_repeat_count": repeat_count,
            "transition": transition,
            "after_diagnostic_category": after.diagnostic_category,
            "before_obligations": copy.deepcopy(before.obligations),
            "after_obligations": copy.deepcopy(after.obligations),
        }
        for name in OBLIGATIONS:
            row[f"obligation_{name}"] = before.obligations[name]
        rows.append(row)

        duration = command.get("duration_seconds")
        if isinstance(duration, (int, float)) and not isinstance(duration, bool):
            duration_used += max(0.0, float(duration))
        state = after
        previous_transition = transition
    return rows


def extract_all_rows(
    manifest: dict[str, Any],
    sessions_root: Path = DEFAULT_SESSIONS_ROOT,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in manifest["inputs"]:
        rows.extend(extract_rows_for_record(record, sessions_root))
    return rows


def _manual_selection_key(project_family: str, command_id: str) -> str:
    return hashlib.sha256(f"{project_family}\0{command_id}".encode()).hexdigest()


def generate_manual_audit_template(
    manifest: dict[str, Any],
    sessions_root: Path = DEFAULT_SESSIONS_ROOT,
) -> dict[str, Any]:
    candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in manifest["inputs"]:
        session_path = sessions_root / record["session_path"]
        session = _read_allowed_session(session_path)
        log_map = _manifest_log_map(record)
        eligible_prefix: list[dict[str, Any]] = []
        eligible_index = 0
        for command in session["commands"]:
            if command.get("role") not in ELIGIBLE_ROLES:
                continue
            eligible_index += 1
            log_ref = log_map[command["command_id"]]
            eligible_prefix.append(
                {
                    "command_id": command["command_id"],
                    "role": command["role"],
                    "exit_code": command["exit_code"],
                    "timed_out": bool(command["timed_out"]),
                    "termination": command["termination"],
                    "log_path": log_ref["path"],
                    "log_sha256": log_ref["sha256"],
                }
            )
            candidates[record["build_system"]].append(
                {
                    "selection_hash": _manual_selection_key(
                        record["project_family"], command["command_id"]
                    ),
                    "split": record["split"],
                    "session_path": record["session_path"],
                    "project_family": record["project_family"],
                    "build_system": record["build_system"],
                    "commit_sha": record["commit_sha"],
                    "command_id": command["command_id"],
                    "eligible_command_index": eligible_index,
                    "evidence_prefix": copy.deepcopy(eligible_prefix),
                    "annotation": None,
                }
            )

    annotations: list[dict[str, Any]] = []
    for system in BUILD_SYSTEMS:
        selected = sorted(candidates[system], key=lambda item: item["selection_hash"])[
            :4
        ]
        if len(selected) != 4:
            raise QualificationError(f"{system} 人工审计候选不足 4 项")
        for index, item in enumerate(selected, 1):
            item["audit_id"] = f"{system}-{index:02d}"
            annotations.append(item)
    return {
        "schema_version": MANUAL_SCHEMA,
        "identity": IDENTITY,
        "issue": ISSUE_URL,
        "selection": {
            "algorithm": "每个构建系统按 SHA-256(project_family + NUL + command_id) 取最小 4 项",
            "uses_transition_label": False,
            "count": len(annotations),
        },
        "annotations": annotations,
    }


def evaluate_manual_audit(
    fixture: dict[str, Any],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    if fixture.get("schema_version") != MANUAL_SCHEMA:
        raise QualificationError("人工审计 fixture schema_version 不匹配")
    row_map = {(row["session_path"], row["command_id"]): row for row in rows}
    obligation_matches = 0
    obligation_total = 0
    transition_matches = 0
    transition_total = 0
    diagnostic_matches = 0
    diagnostic_total = 0
    mismatches: list[dict[str, Any]] = []
    for item in fixture.get("annotations", []):
        if not isinstance(item, dict):
            raise QualificationError("人工审计 annotation item 非对象")
        key = (item.get("session_path"), item.get("command_id"))
        row = row_map.get(key)
        if row is None:
            raise QualificationError(f"人工审计引用不存在的 command: {key}")
        annotation = item.get("annotation")
        if not isinstance(annotation, dict):
            raise QualificationError(f"人工审计尚未填写: {item.get('audit_id')}")
        local_mismatches: list[str] = []
        for side in ("before", "after"):
            expected = annotation.get(f"{side}_obligations")
            if not isinstance(expected, dict) or set(expected) != set(OBLIGATIONS):
                raise QualificationError(
                    f"人工审计 {item.get('audit_id')} 的 {side}_obligations 不完整"
                )
            actual = row[f"{side}_obligations"]
            for name in OBLIGATIONS:
                obligation_total += 1
                if expected[name] == actual[name]:
                    obligation_matches += 1
                else:
                    local_mismatches.append(
                        f"{side}.{name}: human={expected[name]} extractor={actual[name]}"
                    )
        for key_name, row_name in (
            ("before_diagnostic_category", "prior_error_category"),
            ("after_diagnostic_category", "after_diagnostic_category"),
        ):
            diagnostic_total += 1
            if annotation.get(key_name) == row[row_name]:
                diagnostic_matches += 1
            else:
                local_mismatches.append(
                    f"{key_name}: human={annotation.get(key_name)} extractor={row[row_name]}"
                )
        transition_total += 1
        if annotation.get("transition") == row["transition"]:
            transition_matches += 1
        else:
            local_mismatches.append(
                f"transition: human={annotation.get('transition')} extractor={row['transition']}"
            )
        if local_mismatches:
            mismatches.append(
                {
                    "audit_id": item.get("audit_id"),
                    "differences": local_mismatches,
                }
            )
    if transition_total != 12:
        raise QualificationError(f"人工审计必须恰有 12 项，实际 {transition_total}")
    obligation_agreement = obligation_matches / obligation_total
    transition_agreement = transition_matches / transition_total
    return {
        "item_count": transition_total,
        "obligation_field_count": obligation_total,
        "obligation_agreement": round(obligation_agreement, 6),
        "diagnostic_agreement": round(diagnostic_matches / diagnostic_total, 6),
        "transition_agreement": round(transition_agreement, 6),
        "passed": obligation_agreement >= 0.90 and transition_agreement >= 0.90,
        "mismatches": mismatches,
    }


def _aligned_probabilities(
    model: Pipeline,
    frame: pd.DataFrame,
) -> np.ndarray:
    raw = model.predict_proba(frame)
    model_classes = list(model.named_steps["classifier"].classes_)
    probabilities = np.zeros((len(frame), len(TRANSITIONS)), dtype=float)
    for column, label in enumerate(model_classes):
        probabilities[:, TRANSITIONS.index(label)] = raw[:, column]
    probabilities = np.clip(probabilities, 1e-15, 1.0)
    probabilities /= probabilities.sum(axis=1, keepdims=True)
    return probabilities


def _fit_model(
    model_name: str,
    development: pd.DataFrame,
    evaluation: pd.DataFrame,
) -> tuple[np.ndarray, list[str]]:
    numeric = NUMERIC_FEATURES[model_name]
    categorical = CATEGORICAL_FEATURES[model_name]
    transformers: list[tuple[str, Any, list[str]]] = []
    if numeric:
        transformers.append(("numeric", StandardScaler(), numeric))
    if categorical:
        transformers.append(
            (
                "categorical",
                OneHotEncoder(handle_unknown="ignore"),
                categorical,
            )
        )
    pipeline = Pipeline(
        steps=[
            (
                "features",
                ColumnTransformer(transformers=transformers, remainder="drop"),
            ),
            (
                "classifier",
                LogisticRegression(
                    C=1.0,
                    penalty="l2",
                    solver="lbfgs",
                    max_iter=2000,
                    random_state=RANDOM_SEED,
                ),
            ),
        ]
    )
    feature_columns = [*numeric, *categorical]
    pipeline.fit(development[feature_columns], development["transition"])
    return _aligned_probabilities(
        pipeline, evaluation[feature_columns]
    ), feature_columns


def _row_losses(labels: Iterable[str], probabilities: np.ndarray) -> np.ndarray:
    indices = np.array([TRANSITIONS.index(label) for label in labels], dtype=int)
    return -np.log(probabilities[np.arange(len(indices)), indices])


def _row_brier(labels: Iterable[str], probabilities: np.ndarray) -> np.ndarray:
    indices = np.array([TRANSITIONS.index(label) for label in labels], dtype=int)
    targets = np.zeros_like(probabilities)
    targets[np.arange(len(indices)), indices] = 1.0
    return np.sum((probabilities - targets) ** 2, axis=1)


def _model_metrics(
    evaluation: pd.DataFrame,
    probabilities: np.ndarray,
) -> dict[str, Any]:
    predicted = np.array(
        [TRANSITIONS[index] for index in np.argmax(probabilities, axis=1)]
    )
    losses = _row_losses(evaluation["transition"], probabilities)
    brier = _row_brier(evaluation["transition"], probabilities)
    frame = evaluation[["project_family", "build_system", "transition"]].copy()
    frame["log_loss"] = losses
    frame["brier"] = brier
    frame["correct"] = predicted == evaluation["transition"].to_numpy()
    family_rows: list[dict[str, Any]] = []
    for family, group in frame.groupby("project_family", sort=True):
        indices = group.index.to_numpy()
        actual = evaluation.loc[indices, "transition"].to_numpy()
        family_predicted = predicted[indices]
        family_rows.append(
            {
                "project_family": family,
                "build_system": group["build_system"].iloc[0],
                "row_count": len(group),
                "log_loss": float(group["log_loss"].mean()),
                "brier": float(group["brier"].mean()),
                "accuracy": float(group["correct"].mean()),
                "macro_f1": float(
                    f1_score(
                        actual,
                        family_predicted,
                        labels=list(TRANSITIONS),
                        average="macro",
                        zero_division=0,
                    )
                ),
            }
        )
    systems: dict[str, Any] = {}
    for system in BUILD_SYSTEMS:
        items = [item for item in family_rows if item["build_system"] == system]
        systems[system] = {
            "project_family_count": len(items),
            "log_loss": float(np.mean([item["log_loss"] for item in items])),
        }
    return {
        "project_family_macro": {
            metric: float(np.mean([item[metric] for item in family_rows]))
            for metric in ("log_loss", "brier", "accuracy", "macro_f1")
        },
        "by_build_system": systems,
        "by_project_family": family_rows,
        "row_accuracy": float(accuracy_score(evaluation["transition"], predicted)),
    }


def _bootstrap_primary_delta(
    simple_metrics: dict[str, Any],
    state_metrics: dict[str, Any],
) -> dict[str, Any]:
    simple = {
        item["project_family"]: item["log_loss"]
        for item in simple_metrics["by_project_family"]
    }
    state = {
        item["project_family"]: item["log_loss"]
        for item in state_metrics["by_project_family"]
    }
    families = sorted(simple)
    if families != sorted(state):
        raise QualificationError("模型的项目族集合不一致")
    deltas = np.array([state[family] - simple[family] for family in families])
    rng = np.random.default_rng(RANDOM_SEED)
    sampled = rng.choice(deltas, size=(BOOTSTRAP_SAMPLES, len(deltas)), replace=True)
    means = sampled.mean(axis=1)
    return {
        "definition": "progress_state - simple_combined；负值表示状态更好",
        "project_family_count": len(families),
        "mean_delta": float(deltas.mean()),
        "bootstrap_samples": BOOTSTRAP_SAMPLES,
        "seed": RANDOM_SEED,
        "confidence_interval_95": {
            "lower": float(np.quantile(means, 0.025)),
            "upper": float(np.quantile(means, 0.975)),
        },
        "improved_project_family_count": int(np.sum(deltas < 0)),
        "per_project_family": [
            {"project_family": family, "delta": float(delta)}
            for family, delta in zip(families, deltas, strict=True)
        ],
    }


def _label_coverage(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for split in ("development", "evaluation"):
        counts = Counter(row["transition"] for row in rows if row["split"] == split)
        result[split] = {
            "counts": {label: counts[label] for label in TRANSITIONS},
            "all_four_observed": all(counts[label] > 0 for label in TRANSITIONS),
        }
    result["passed"] = all(
        result[split]["all_four_observed"] for split in ("development", "evaluation")
    )
    return result


def _gate_results(
    source_integrity: dict[str, Any],
    coverage: dict[str, Any],
    manual: dict[str, Any],
    metrics: dict[str, Any] | None,
    primary: dict[str, Any] | None,
) -> dict[str, Any]:
    gates: list[dict[str, Any]] = [
        {
            "name": "input_integrity_and_isolation",
            "passed": bool(source_integrity.get("verified")),
            "observed": source_integrity.get("verified"),
            "threshold": True,
        },
        {
            "name": "four_class_coverage",
            "passed": bool(coverage["passed"]),
            "observed": {
                split: coverage[split]["counts"]
                for split in ("development", "evaluation")
            },
            "threshold": "每个 split 四类均至少 1 项",
        },
        {
            "name": "manual_reconstruction",
            "passed": bool(manual["passed"]),
            "observed": {
                "obligation_agreement": manual["obligation_agreement"],
                "transition_agreement": manual["transition_agreement"],
            },
            "threshold": {
                "obligation_agreement": 0.90,
                "transition_agreement": 0.90,
            },
        },
    ]
    if metrics is not None and primary is not None:
        simple = metrics["simple_combined"]
        state = metrics["progress_state"]
        log_loss_improvement = (
            simple["project_family_macro"]["log_loss"]
            - state["project_family_macro"]["log_loss"]
        )
        brier_delta = (
            state["project_family_macro"]["brier"]
            - simple["project_family_macro"]["brier"]
        )
        system_deltas = {
            system: (
                state["by_build_system"][system]["log_loss"]
                - simple["by_build_system"][system]["log_loss"]
            )
            for system in BUILD_SYSTEMS
        }
        gates.extend(
            [
                {
                    "name": "minimum_log_loss_improvement",
                    "passed": log_loss_improvement >= 0.05,
                    "observed": log_loss_improvement,
                    "threshold": 0.05,
                },
                {
                    "name": "bootstrap_upper_below_zero",
                    "passed": primary["confidence_interval_95"]["upper"] < 0,
                    "observed": primary["confidence_interval_95"]["upper"],
                    "threshold": 0,
                },
                {
                    "name": "brier_non_degradation",
                    "passed": brier_delta <= 0.01,
                    "observed": brier_delta,
                    "threshold": 0.01,
                },
                {
                    "name": "cross_build_system_consistency",
                    "passed": (
                        sum(delta < 0 for delta in system_deltas.values()) >= 2
                        and max(system_deltas.values()) <= 0.10
                    ),
                    "observed": system_deltas,
                    "threshold": {
                        "improved_systems": 2,
                        "maximum_degradation": 0.10,
                    },
                },
            ]
        )
    passed = len(gates) == 7 and all(item["passed"] for item in gates)
    if not coverage["passed"]:
        decision = "stop_existing_assets_insufficient"
        interpretation = (
            "现有只读资产未覆盖开发集和测试集中的全部四类转移，不能评价状态机制。"
        )
    elif not manual["passed"]:
        decision = "stop_extractor_not_qualified"
        interpretation = "状态重建未通过人工一致性门禁，不能运行或解释增量比较。"
    elif passed:
        decision = "proceed_to_budget_action_experiment_design"
        interpretation = "偏序状态通过冻结增量门槛，可另行设计预算动作干预；本结果仍不是 controller 效果。"
    else:
        decision = "abandon_current_progress_state_mechanism"
        interpretation = "输入与重建门禁已闭合，但偏序状态未通过冻结的增量信息门槛。"
    return {
        "passed": passed,
        "decision": decision,
        "interpretation": interpretation,
        "gates": gates,
    }


def build_report(
    manifest_path: Path = DEFAULT_MANIFEST,
    manual_audit_path: Path = DEFAULT_MANUAL_AUDIT,
    sessions_root: Path = DEFAULT_SESSIONS_ROOT,
) -> dict[str, Any]:
    manifest = load_json(manifest_path, "input manifest")
    source_integrity = verify_input_manifest(manifest, sessions_root)
    rows = extract_all_rows(manifest, sessions_root)
    coverage = _label_coverage(rows)
    manual_fixture = load_json(manual_audit_path, "manual audit")
    manual = evaluate_manual_audit(manual_fixture, rows)

    metrics: dict[str, Any] | None = None
    primary: dict[str, Any] | None = None
    model_features: dict[str, Any] | None = None
    if coverage["passed"] and manual["passed"]:
        frame = pd.DataFrame(rows)
        development = frame[frame["split"] == "development"].reset_index(drop=True)
        evaluation = frame[frame["split"] == "evaluation"].reset_index(drop=True)
        metrics = {}
        model_features = {}
        for model_name in NUMERIC_FEATURES:
            probabilities, feature_columns = _fit_model(
                model_name,
                development,
                evaluation,
            )
            metrics[model_name] = _model_metrics(evaluation, probabilities)
            model_features[model_name] = feature_columns
        primary = _bootstrap_primary_delta(
            metrics["simple_combined"],
            metrics["progress_state"],
        )

    decision = _gate_results(
        source_integrity,
        coverage,
        manual,
        metrics,
        primary,
    )
    split_summary = {}
    for split in ("development", "evaluation"):
        selected = [row for row in rows if row["split"] == split]
        split_summary[split] = {
            "row_count": len(selected),
            "project_family_count": len({row["project_family"] for row in selected}),
            "sessions": len({row["session_path"] for row in selected}),
            "rows_by_build_system": {
                system: sum(row["build_system"] == system for row in selected)
                for system in BUILD_SYSTEMS
            },
        }
    return {
        "schema_version": REPORT_SCHEMA,
        "identity": IDENTITY,
        "issue": ISSUE_URL,
        "analysis_date": "2026-10-09",
        "work_type": "infrastructure_and_result_analysis",
        "provider_calls": 0,
        "credential_reads": 0,
        "formal_attempts": 0,
        "hidden_answers_read": False,
        "source_integrity": {
            **source_integrity,
            "manifest_file_sha256": file_sha256(manifest_path),
            "preregistration_sha256": file_sha256(PREREGISTRATION),
            "manual_audit_sha256": file_sha256(manual_audit_path),
            "analysis_script_sha256": file_sha256(SCRIPT_PATH),
        },
        "observed_input": split_summary,
        "derived_transition_coverage": coverage,
        "manual_reconstruction_audit": manual,
        "model_specification": {
            "library": "scikit-learn",
            "classifier": "LogisticRegression",
            "C": 1.0,
            "penalty": "l2",
            "solver": "lbfgs",
            "max_iter": 2000,
            "random_state": RANDOM_SEED,
            "features": model_features,
        },
        "metrics": metrics,
        "primary_comparison": primary,
        "decision": decision,
        "claim_boundary": {
            "supported": [
                "固定输入上的状态重建一致性",
                "固定 observed-action 转移标签上的隔离预测增量或缺失",
                "是否达到进入后续预算动作实验设计的预注册门槛",
            ],
            "unsupported": [
                "未选择动作的反事实效果",
                "controller treatment effect",
                "strict success、时间、token 或费用改善",
                "跨更广项目总体的泛化",
                "模型排名、统计显著性或全球首次",
            ],
        },
    }


def _fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return "未估计"
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        return f"{value:.{digits}f}"
    return str(value)


def render_markdown(report: dict[str, Any]) -> str:
    observed = report["observed_input"]
    coverage = report["derived_transition_coverage"]
    manual = report["manual_reconstruction_audit"]
    decision = report["decision"]
    lines = [
        "# 跨构建系统进展状态 v1 离线资格审计结果",
        "",
        "> 日期：2026-10-09",
        f"> Tracking Issue：[{ISSUE_URL.rsplit('/', 1)[-1]}]({ISSUE_URL})",
        f"> Identity：`{IDENTITY}`",
        "> 类型：基础设施与结果分析；0 Provider、0 credential read、0 formal attempt",
        "",
        "## 1. 结论",
        "",
        f"**决定：`{decision['decision']}`。** {decision['interpretation']}",
        "",
        "本报告只评价固定历史轨迹中实际已选动作后的短期状态转移。它不估计未选动作、controller 因果效果或 strict success 改善。",
        "",
        "## 2. 输入与隔离",
        "",
        "| Split | Session | 项目族 | 决策点 | CMake | Make | Autotools |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for split in ("development", "evaluation"):
        item = observed[split]
        by_system = item["rows_by_build_system"]
        lines.append(
            f"| `{split}` | {item['sessions']} | {item['project_family_count']} | {item['row_count']} | {by_system['cmake']} | {by_system['make']} | {by_system['autotools']} |"
        )
    lines.extend(
        [
            "",
            f"输入清单闭合：`{report['source_integrity']['verified']}`；manifest canonical SHA-256：`{report['source_integrity']['manifest_sha256']}`。开发/测试项目族零重合，且测试轨迹时间严格晚于开发轨迹。",
            "",
            "## 3. 状态重建门禁",
            "",
            f"人工审计 {manual['item_count']} 个按哈希选择、未按标签抽样的决策点：obligation 字段一致率 "
            f"`{_fmt(manual['obligation_agreement'])}`，诊断一致率 `{_fmt(manual['diagnostic_agreement'])}`，"
            f"transition 一致率 `{_fmt(manual['transition_agreement'])}`；门禁 `{'通过' if manual['passed'] else '失败'}`。",
            "",
            "四类转移覆盖：",
            "",
            "| Split | progress | lateral | stagnation | regression | 全覆盖 |",
            "| --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for split in ("development", "evaluation"):
        counts = coverage[split]["counts"]
        lines.append(
            f"| `{split}` | {counts['progress']} | {counts['lateral']} | {counts['stagnation']} | {counts['regression']} | {'是' if coverage[split]['all_four_observed'] else '否'} |"
        )

    metrics = report["metrics"]
    if metrics is not None:
        lines.extend(
            [
                "",
                "## 4. 隔离比较",
                "",
                "项目族内先平均，再对 12 个未见项目族宏平均。",
                "",
                "| 特征组 | Log loss | Brier | Accuracy | Macro F1 |",
                "| --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for name in NUMERIC_FEATURES:
            macro = metrics[name]["project_family_macro"]
            lines.append(
                f"| `{name}` | {_fmt(macro['log_loss'])} | {_fmt(macro['brier'])} | {_fmt(macro['accuracy'])} | {_fmt(macro['macro_f1'])} |"
            )
        primary = report["primary_comparison"]
        interval = primary["confidence_interval_95"]
        lines.extend(
            [
                "",
                f"主要差值 `progress_state - simple_combined` 为 `{_fmt(primary['mean_delta'])}` nat，"
                f"项目族 bootstrap 95% 区间 `[{_fmt(interval['lower'])}, {_fmt(interval['upper'])}]`；"
                f"{primary['improved_project_family_count']}/{primary['project_family_count']} 个项目族改善。",
                "",
                "按构建系统的 log-loss 差值：",
                "",
                "| 构建系统 | progress_state - simple_combined |",
                "| --- | ---: |",
            ]
        )
        for system in BUILD_SYSTEMS:
            delta = (
                metrics["progress_state"]["by_build_system"][system]["log_loss"]
                - metrics["simple_combined"]["by_build_system"][system]["log_loss"]
            )
            lines.append(f"| `{system}` | {_fmt(delta)} |")
    else:
        lines.extend(
            [
                "",
                "## 4. 隔离比较",
                "",
                "预注册的数据覆盖或人工重建前置门禁未通过，因此没有拟合或报告最终统计模型。",
            ]
        )

    lines.extend(
        [
            "",
            "## 5. 预注册门槛",
            "",
            "| 门槛 | 观测 | 通过 |",
            "| --- | --- | --- |",
        ]
    )
    for gate in decision["gates"]:
        observed_text = json.dumps(gate["observed"], ensure_ascii=False, sort_keys=True)
        lines.append(
            f"| `{gate['name']}` | `{observed_text}` | {'是' if gate['passed'] else '否'} |"
        )
    lines.extend(
        [
            "",
            "## 6. 解释边界",
            "",
            "能够支持：",
            "",
            *(f"- {item}；" for item in report["claim_boundary"]["supported"]),
            "",
            "不能支持：",
            "",
            *(f"- {item}；" for item in report["claim_boundary"]["unsupported"]),
            "",
            "所有旧 experiment identity 和 evidence 在本审计中保持只读。",
            "",
        ]
    )
    return "\n".join(lines)


def _show_manual_evidence(
    fixture: dict[str, Any],
    audit_id: str,
    sessions_root: Path,
) -> None:
    items = [
        item
        for item in fixture.get("annotations", [])
        if item.get("audit_id") == audit_id
    ]
    if len(items) != 1:
        raise QualificationError(f"未知 audit_id: {audit_id}")
    item = items[0]
    print(
        json.dumps(
            {
                key: item[key]
                for key in (
                    "audit_id",
                    "split",
                    "session_path",
                    "project_family",
                    "build_system",
                    "command_id",
                    "eligible_command_index",
                )
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    for index, evidence in enumerate(item["evidence_prefix"], 1):
        path = sessions_root / evidence["log_path"]
        print(
            f"\n--- prefix {index}: role={evidence['role']} exit={evidence['exit_code']} timeout={evidence['timed_out']} termination={evidence['termination']} ---"
        )
        print(_diagnostic_text(path))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sessions-root",
        type=Path,
        default=DEFAULT_SESSIONS_ROOT,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    inventory = subparsers.add_parser("inventory")
    inventory.add_argument("--output", type=Path, default=DEFAULT_MANIFEST)

    manual = subparsers.add_parser("manual-template")
    manual.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    manual.add_argument("--output", type=Path, default=DEFAULT_MANUAL_AUDIT)

    evidence = subparsers.add_parser("show-manual-evidence")
    evidence.add_argument("audit_id")
    evidence.add_argument("--fixture", type=Path, default=DEFAULT_MANUAL_AUDIT)

    run = subparsers.add_parser("run")
    run.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    run.add_argument("--manual-audit", type=Path, default=DEFAULT_MANUAL_AUDIT)
    run.add_argument("--json-output", type=Path, default=DEFAULT_JSON_REPORT)
    run.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN_REPORT)

    check = subparsers.add_parser("check")
    check.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    check.add_argument("--manual-audit", type=Path, default=DEFAULT_MANUAL_AUDIT)
    check.add_argument("--json-report", type=Path, default=DEFAULT_JSON_REPORT)
    check.add_argument("--markdown-report", type=Path, default=DEFAULT_MARKDOWN_REPORT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "inventory":
            manifest = generate_input_manifest(args.sessions_root)
            write_json(args.output, manifest)
            print(
                json.dumps(
                    {
                        "output": str(args.output),
                        "canonical_sha256": canonical_sha256(manifest),
                        "summary": manifest["summary"],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        elif args.command == "manual-template":
            manifest = load_json(args.manifest, "input manifest")
            verify_input_manifest(manifest, args.sessions_root)
            fixture = generate_manual_audit_template(manifest, args.sessions_root)
            write_json(args.output, fixture)
            print(
                json.dumps(
                    {
                        "output": str(args.output),
                        "canonical_sha256": canonical_sha256(fixture),
                        "count": fixture["selection"]["count"],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        elif args.command == "show-manual-evidence":
            fixture = load_json(args.fixture, "manual audit")
            _show_manual_evidence(fixture, args.audit_id, args.sessions_root)
        elif args.command == "run":
            report = build_report(
                args.manifest,
                args.manual_audit,
                args.sessions_root,
            )
            write_json(args.json_output, report)
            args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
            args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
            print(
                json.dumps(
                    {
                        "decision": report["decision"],
                        "json_output": str(args.json_output),
                        "markdown_output": str(args.markdown_output),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        elif args.command == "check":
            expected = build_report(
                args.manifest,
                args.manual_audit,
                args.sessions_root,
            )
            committed = load_json(args.json_report, "qualification report")
            if expected != committed:
                raise QualificationError("提交的 JSON 报告不能从冻结输入重建")
            expected_markdown = render_markdown(expected)
            if args.markdown_report.read_text(encoding="utf-8") != expected_markdown:
                raise QualificationError("提交的 Markdown 报告不能从 JSON 确定性重建")
            print(
                json.dumps(
                    {
                        "verified": True,
                        "decision": expected["decision"],
                        "report_sha256": file_sha256(args.json_report),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:  # pragma: no cover
            raise QualificationError(f"未知命令: {args.command}")
    except QualificationError as exc:
        print(f"qualification error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
