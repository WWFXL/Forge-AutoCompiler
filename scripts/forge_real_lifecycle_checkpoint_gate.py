#!/usr/bin/env python3
"""验证 failure checkpoint 与真实 Session/Docker 生命周期接线的无模型门禁。"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import sqlite3
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, TypedDict

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    ToolMessage,
    message_to_dict,
)
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

import forge_budget_checkpoint_prototype as budget_checkpoint
import forge_environment_checkpoint_prototype as environment_checkpoint

SCHEMA_VERSION = "forge-real-lifecycle-checkpoint-1.0.0"
CAPTURE_POINT = "after-neutral-tool-message-before-continuation"
CONTINUATION_NODE = "continue_model"
BASELINE_ARM = "baseline"
TREATMENT_ARM = "treatment"
ARMS = (BASELINE_ARM, TREATMENT_ARM)
CAPTURE_LABEL = "forge.checkpoint.capture_id"
ROLE_LABEL = "forge.checkpoint.role"
PHASES = frozenset(
    {
        "preparing",
        "message_frozen",
        "environment_frozen",
        "budget_frozen",
        "committed",
        "aborted",
        "cleanup_pending",
        "cleaned",
    }
)
TRANSITIONS = {
    "preparing": {"message_frozen", "aborted", "cleanup_pending"},
    "message_frozen": {"environment_frozen", "aborted", "cleanup_pending"},
    "environment_frozen": {"budget_frozen", "aborted", "cleanup_pending"},
    "budget_frozen": {"committed", "aborted", "cleanup_pending"},
    "committed": {"cleanup_pending"},
    "aborted": {"cleanup_pending", "cleaned"},
    "cleanup_pending": {"cleaned"},
    "cleaned": set(),
}
_ID_RE = re.compile(r"[a-z][a-z0-9-]{0,63}")


class LifecycleGateError(RuntimeError):
    pass


class SimulatedCrash(LifecycleGateError):
    """只供测试在持久边界模拟进程突然退出。"""


class LifecycleMessageState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    capture_id: str
    arm: str
    session_id: str


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest_payload_sha256(manifest: dict[str, Any]) -> str:
    return sha256_bytes(
        canonical_bytes(
            {key: value for key, value in manifest.items() if key != "manifest_sha256"}
        )
    )


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
        raise LifecycleGateError(f"{label} is invalid")
    return value


def _safe_path_component(value: str) -> str:
    _identifier(value, "capture_id")
    return value


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        if os.name == "posix":
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def _merge(target: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(target)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


@dataclass(frozen=True)
class CaptureRecord:
    capture_id: str
    phase: str
    revision: int
    lease_owner: str | None
    lease_expires_at: float | None
    payload: dict[str, Any]
    last_error: str | None


@dataclass
class LifecycleArm:
    arm: str
    session: Any
    message_config: dict[str, Any]
    budget: budget_checkpoint.BudgetCheckpointRuntime


class CaptureCoordinator:
    """用 SQLite CAS/lease 持久化跨资源 capture 状态。"""

    def __init__(
        self, database: Path, *, clock: Callable[[], float] = time.time
    ) -> None:
        self.database = database
        self.clock = clock
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self._setup()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    def _setup(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS checkpoint_capture (
                    capture_id TEXT PRIMARY KEY,
                    phase TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    lease_owner TEXT,
                    lease_expires_at REAL,
                    payload_json TEXT NOT NULL,
                    last_error TEXT
                )
                """
            )

    @staticmethod
    def _record(row: sqlite3.Row) -> CaptureRecord:
        return CaptureRecord(
            capture_id=row["capture_id"],
            phase=row["phase"],
            revision=row["revision"],
            lease_owner=row["lease_owner"],
            lease_expires_at=row["lease_expires_at"],
            payload=json.loads(row["payload_json"]),
            last_error=row["last_error"],
        )

    def get(self, capture_id: str) -> CaptureRecord:
        _identifier(capture_id, "capture_id")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM checkpoint_capture WHERE capture_id = ?",
                (capture_id,),
            ).fetchone()
        if row is None:
            raise LifecycleGateError(f"unknown capture: {capture_id}")
        return self._record(row)

    def create(self, capture_id: str, payload: dict[str, Any]) -> CaptureRecord:
        _identifier(capture_id, "capture_id")
        encoded = canonical_bytes(payload).decode("utf-8")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM checkpoint_capture WHERE capture_id = ?",
                (capture_id,),
            ).fetchone()
            if existing is None:
                connection.execute(
                    "INSERT INTO checkpoint_capture VALUES (?, 'preparing', 0, NULL, NULL, ?, NULL)",
                    (capture_id, encoded),
                )
            elif (
                existing["payload_json"] != encoded and existing["phase"] == "preparing"
            ):
                raise LifecycleGateError(
                    "capture identity was reused with different initial state"
                )
            connection.commit()
        return self.get(capture_id)

    def acquire(
        self, capture_id: str, owner: str, *, ttl_seconds: float = 900
    ) -> CaptureRecord:
        _identifier(owner, "lease_owner")
        now = self.clock()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM checkpoint_capture WHERE capture_id = ?",
                (capture_id,),
            ).fetchone()
            if row is None:
                raise LifecycleGateError(f"unknown capture: {capture_id}")
            if (
                row["lease_owner"] not in (None, owner)
                and row["lease_expires_at"] is not None
                and row["lease_expires_at"] > now
            ):
                raise LifecycleGateError(
                    "capture lease is owned by another coordinator"
                )
            connection.execute(
                "UPDATE checkpoint_capture SET lease_owner = ?, lease_expires_at = ?, revision = revision + 1 WHERE capture_id = ? AND revision = ?",
                (owner, now + ttl_seconds, capture_id, row["revision"]),
            )
            if connection.total_changes != 1:
                raise LifecycleGateError("capture lease CAS failed")
            connection.commit()
        return self.get(capture_id)

    def update(
        self,
        capture_id: str,
        owner: str,
        *,
        patch: dict[str, Any] | None = None,
        expected_phase: str | None = None,
        target_phase: str | None = None,
        last_error: str | None = None,
        ttl_seconds: float = 900,
    ) -> CaptureRecord:
        now = self.clock()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM checkpoint_capture WHERE capture_id = ?",
                (capture_id,),
            ).fetchone()
            if row is None:
                raise LifecycleGateError(f"unknown capture: {capture_id}")
            if (
                row["lease_owner"] != owner
                or row["lease_expires_at"] is None
                or row["lease_expires_at"] <= now
            ):
                raise LifecycleGateError(
                    "capture update requires a live matching lease"
                )
            phase = row["phase"]
            if expected_phase is not None and phase != expected_phase:
                raise LifecycleGateError(
                    f"capture phase drifted: expected {expected_phase}, got {phase}"
                )
            next_phase = target_phase or phase
            if next_phase not in PHASES:
                raise LifecycleGateError(f"unknown capture phase: {next_phase}")
            if next_phase != phase and next_phase not in TRANSITIONS[phase]:
                raise LifecycleGateError(
                    f"illegal capture transition: {phase} -> {next_phase}"
                )
            payload = _merge(json.loads(row["payload_json"]), patch or {})
            connection.execute(
                """
                UPDATE checkpoint_capture
                SET phase = ?, revision = revision + 1, lease_expires_at = ?, payload_json = ?, last_error = ?
                WHERE capture_id = ? AND revision = ?
                """,
                (
                    next_phase,
                    now + ttl_seconds,
                    canonical_bytes(payload).decode("utf-8"),
                    last_error,
                    capture_id,
                    row["revision"],
                ),
            )
            if connection.total_changes != 1:
                raise LifecycleGateError("capture update CAS failed")
            connection.commit()
        return self.get(capture_id)

    def release(self, capture_id: str, owner: str) -> CaptureRecord:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT revision, lease_owner FROM checkpoint_capture WHERE capture_id = ?",
                (capture_id,),
            ).fetchone()
            if row is None:
                raise LifecycleGateError(f"unknown capture: {capture_id}")
            if row["lease_owner"] not in (None, owner):
                raise LifecycleGateError(
                    "capture lease is owned by another coordinator"
                )
            connection.execute(
                "UPDATE checkpoint_capture SET lease_owner = NULL, lease_expires_at = NULL, revision = revision + 1 WHERE capture_id = ? AND revision = ?",
                (capture_id, row["revision"]),
            )
            connection.commit()
        return self.get(capture_id)


class LifecycleMessageRuntime:
    """在真实 submit callback 后持久化中性 ToolMessage 的实验图。"""

    def __init__(
        self,
        checkpointer: Any,
        submit_callback: Callable[[], str],
        *,
        repair_packet: dict[str, Any] | None = None,
    ) -> None:
        self.submit_callback = submit_callback
        self.repair_packet = copy.deepcopy(repair_packet)
        self.submit_calls = 0
        self.continuation_calls = 0
        graph = StateGraph(LifecycleMessageState)
        graph.add_node("request_submit", self._request_submit)
        graph.add_node("submit", self._submit)
        graph.add_node(CONTINUATION_NODE, self._continue)
        graph.add_edge(START, "request_submit")
        graph.add_edge("request_submit", "submit")
        graph.add_edge("submit", CONTINUATION_NODE)
        graph.add_edge(CONTINUATION_NODE, END)
        self.graph = graph.compile(
            checkpointer=checkpointer, interrupt_before=[CONTINUATION_NODE]
        )

    @staticmethod
    def config(thread_id: str) -> dict[str, dict[str, str]]:
        return {"configurable": {"thread_id": thread_id}}

    @staticmethod
    def _request_submit(_state: LifecycleMessageState) -> dict[str, list[AIMessage]]:
        return {
            "messages": [
                AIMessage(
                    content="",
                    id="lifecycle-submit-request",
                    tool_calls=[
                        {
                            "name": "submit_build_result",
                            "args": {},
                            "id": "lifecycle-submit-call",
                            "type": "tool_call",
                        }
                    ],
                )
            ]
        }

    def _submit(self, state: LifecycleMessageState) -> dict[str, list[ToolMessage]]:
        self.submit_calls += 1
        result = self.submit_callback()
        try:
            payload = json.loads(result)
        except (TypeError, json.JSONDecodeError) as exc:
            raise LifecycleGateError("submit callback did not return JSON") from exc
        if not isinstance(payload, dict) or payload.get("status") != "failed":
            raise LifecycleGateError("lifecycle gate requires a failed neutral submit")
        payload.pop("repair_packet", None)
        request = state["messages"][-1]
        return {
            "messages": [
                ToolMessage(
                    content=canonical_bytes(payload).decode("utf-8"),
                    id="lifecycle-submit-feedback",
                    name="submit_build_result",
                    tool_call_id=request.tool_calls[0]["id"],
                )
            ]
        }

    def _continue(self, _state: LifecycleMessageState) -> dict[str, list[AIMessage]]:
        self.continuation_calls += 1
        return {
            "messages": [
                AIMessage(
                    content="deterministic lifecycle continuation completed",
                    id=f"lifecycle-continuation-{self.continuation_calls}",
                )
            ]
        }

    @staticmethod
    def serialize(state: dict[str, Any]) -> dict[str, Any]:
        return {
            "capture_id": state["capture_id"],
            "arm": state["arm"],
            "session_id": state["session_id"],
            "messages": [message_to_dict(message) for message in state["messages"]],
        }

    def capture(
        self, *, capture_id: str, session_id: str, instruction: str
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        thread_id = f"{capture_id}-neutral"
        config = self.config(thread_id)
        self.graph.invoke(
            {
                "messages": [
                    HumanMessage(content=instruction, id="lifecycle-instruction")
                ],
                "capture_id": capture_id,
                "arm": "neutral",
                "session_id": session_id,
            },
            config,
        )
        snapshot = self.graph.get_state(config)
        if tuple(snapshot.next) != (CONTINUATION_NODE,):
            raise LifecycleGateError("message graph did not pause before continuation")
        serialized = self.serialize(snapshot.values)
        checkpoint_id = snapshot.config.get("configurable", {}).get("checkpoint_id")
        descriptor = {
            "thread_id": thread_id,
            "checkpoint_id": checkpoint_id,
            "next_node": CONTINUATION_NODE,
            "tool_call_id": "lifecycle-submit-call",
            "canonical_state_sha256": sha256_bytes(canonical_bytes(serialized)),
        }
        return config, descriptor

    def derive_arm(
        self,
        source_config: dict[str, Any],
        *,
        arm: str,
        thread_id: str,
        session_id: str,
    ) -> dict[str, Any]:
        if arm not in ARMS:
            raise LifecycleGateError("unknown arm")
        source = self.graph.get_state(source_config)
        if tuple(source.next) != (CONTINUATION_NODE,):
            raise LifecycleGateError("neutral message checkpoint is not resumable")
        values = copy.deepcopy(source.values)
        messages = list(values["messages"])
        feedback = messages[-1]
        if not isinstance(feedback, ToolMessage):
            raise LifecycleGateError("neutral feedback ToolMessage is missing")
        content = json.loads(feedback.content)
        if arm == TREATMENT_ARM:
            if self.repair_packet is None:
                raise LifecycleGateError("treatment arm requires a repair packet")
            content["repair_packet"] = copy.deepcopy(self.repair_packet)
        messages[-1] = ToolMessage(
            content=canonical_bytes(content).decode("utf-8"),
            id=feedback.id,
            name=feedback.name,
            tool_call_id=feedback.tool_call_id,
            status=feedback.status,
        )
        values.update(messages=messages, arm=arm, session_id=session_id)
        target = self.config(thread_id)
        self.graph.update_state(target, values, as_node="submit")
        if tuple(self.graph.get_state(target).next) != (CONTINUATION_NODE,):
            raise LifecycleGateError("derived arm is not resumable")
        return target


class LifecycleEnvironmentAdapter:
    """在明确 pause 窗口冻结真实 Compile Session 容器和 bind mounts。"""

    def __init__(
        self,
        runner: Any,
        *,
        local_snapshot_root: Path,
        host_snapshot_root: str | None = None,
    ) -> None:
        self.runner = runner
        self.local_snapshot_root = local_snapshot_root
        self.host_snapshot_root = host_snapshot_root or str(local_snapshot_root)

    @staticmethod
    def _image_id(output: str) -> str:
        return environment_checkpoint.committed_image_id(output)

    @staticmethod
    def _container_paused(runner: Any, container: str) -> bool:
        result = runner.run(
            ["inspect", "--format", "{{.State.Paused}}", container],
            check=False,
            timeout_seconds=30,
        )
        return result.returncode == 0 and result.stdout.strip().lower() == "true"

    def _unpause(self, container: str) -> None:
        if self._container_paused(self.runner, container):
            result = self.runner.run(
                ["unpause", container], check=False, timeout_seconds=30
            )
            if result.returncode != 0:
                raise LifecycleGateError(
                    f"failed to unpause parent container {container}"
                )

    def _archive(
        self,
        *,
        capture_id: str,
        role: str,
        source: str,
        image_id: str,
    ) -> dict[str, Any]:
        helper = f"forge-checkpoint-{capture_id}-{role}"
        archive_name = f"{role}.tar"
        self.runner.run(
            [
                "run",
                "--rm",
                "--name",
                helper,
                "--label",
                f"{CAPTURE_LABEL}={capture_id}",
                "--label",
                f"{ROLE_LABEL}=archive-{role}",
                "--mount",
                f"type=bind,src={source},dst=/source,readonly",
                "--mount",
                f"type=bind,src={self.host_snapshot_root},dst=/snapshot",
                image_id,
                "sh",
                "-c",
                f"tar --numeric-owner --format=posix -cpf /snapshot/{archive_name} -C /source .",
            ],
            timeout_seconds=120,
        )
        archive = self.local_snapshot_root / archive_name
        if not archive.is_file():
            raise LifecycleGateError(f"archive was not created: {archive_name}")
        return {
            "path": str(archive),
            "host_path": f"{self.host_snapshot_root.rstrip('/')}/{archive_name}",
            "sha256": sha256_file(archive),
        }

    def capture(
        self,
        *,
        capture_id: str,
        session: Any,
        bind_sources: dict[str, str],
        arm_plan: dict[str, Any],
        coordinator: CaptureCoordinator,
        owner: str,
        crash_after: str | None = None,
    ) -> dict[str, Any]:
        if not session.container_id or not session.image_id:
            raise LifecycleGateError(
                "parent Compile Session has no live immutable container identity"
            )
        self.local_snapshot_root.mkdir(parents=True, exist_ok=True)
        parent = session.container_id
        coordinator.update(
            capture_id,
            owner,
            expected_phase="message_frozen",
            patch={
                "environment_work": {
                    "parent_container_id": parent,
                    "parent_container_name": session.container_name,
                    "parent_image_id": session.image_id,
                    "snapshot_dir": str(self.local_snapshot_root),
                    "snapshot_host_dir": self.host_snapshot_root,
                    "parent_paused": False,
                    "continuation_image_id": None,
                    "archives": {},
                }
            },
        )
        abrupt = False
        try:
            self.runner.run(["pause", parent], timeout_seconds=30)
            coordinator.update(
                capture_id, owner, patch={"environment_work": {"parent_paused": True}}
            )
            if crash_after == "pause":
                abrupt = True
                raise SimulatedCrash("simulated crash after pause")

            committed = self.runner.run(
                [
                    "commit",
                    "--no-pause",
                    "--change",
                    f"LABEL {CAPTURE_LABEL}={capture_id}",
                    "--change",
                    f"LABEL {ROLE_LABEL}=continuation",
                    parent,
                ],
                timeout_seconds=180,
            )
            continuation_image_id = self._image_id(committed.stdout)
            coordinator.update(
                capture_id,
                owner,
                patch={
                    "environment_work": {"continuation_image_id": continuation_image_id}
                },
            )
            if crash_after == "commit":
                abrupt = True
                raise SimulatedCrash("simulated crash after commit")

            archives: dict[str, Any] = {}
            for role in ("workspace", "artifacts", "logs", "repro"):
                archives[role] = self._archive(
                    capture_id=capture_id,
                    role=role,
                    source=bind_sources[role],
                    image_id=session.image_id,
                )
                coordinator.update(
                    capture_id,
                    owner,
                    patch={"environment_work": {"archives": {role: archives[role]}}},
                )
                if crash_after == f"{role}_archive":
                    abrupt = True
                    raise SimulatedCrash(f"simulated crash after {role} archive")

            manifest = {
                "schema_version": SCHEMA_VERSION,
                "manifest_sha256": "",
                "capture_id": capture_id,
                "parent": {
                    "thread_id": session.thread_id,
                    "session_id": session.session_id,
                    "container_id": parent,
                    "container_name": session.container_name,
                    "image_id": session.image_id,
                },
                "continuation_image_id": continuation_image_id,
                "archives": archives,
                "arm_environments": {
                    arm: arm_plan[arm]["environment_id"] for arm in ARMS
                },
            }
            manifest["manifest_sha256"] = manifest_payload_sha256(manifest)
            manifest_path = self.local_snapshot_root / "environment.json"
            _atomic_write(manifest_path, canonical_bytes(manifest) + b"\n")
            coordinator.update(
                capture_id,
                owner,
                expected_phase="message_frozen",
                target_phase="environment_frozen",
                patch={
                    "environment": {
                        "manifest_path": str(manifest_path),
                        "manifest_sha256": manifest["manifest_sha256"],
                        "continuation_image_id": continuation_image_id,
                    }
                },
            )
            if crash_after == "environment_frozen":
                abrupt = True
                raise SimulatedCrash("simulated crash after environment freeze")
            return manifest
        finally:
            if not abrupt:
                self._unpause(parent)
                coordinator.update(
                    capture_id,
                    owner,
                    patch={"environment_work": {"parent_paused": False}},
                )

    def reconcile_parent(self, record: CaptureRecord) -> None:
        work = record.payload.get("environment_work", {})
        container = work.get("parent_container_id")
        if isinstance(container, str) and container:
            self._unpause(container)
        capture_id = record.capture_id
        for role in ("workspace", "artifacts", "logs", "repro"):
            self.runner.run(
                ["rm", "-f", f"forge-checkpoint-{capture_id}-{role}"],
                check=False,
                timeout_seconds=20,
            )

    def discover_continuation_images(self, capture_id: str) -> list[str]:
        result = self.runner.run(
            [
                "image",
                "ls",
                "-q",
                "--filter",
                f"label={CAPTURE_LABEL}={capture_id}",
                "--filter",
                f"label={ROLE_LABEL}=continuation",
            ],
            check=False,
            timeout_seconds=30,
        )
        return sorted(
            {line.strip() for line in result.stdout.splitlines() if line.strip()}
        )

    def cleanup_partial(self, record: CaptureRecord) -> None:
        self.reconcile_parent(record)
        work = record.payload.get("environment_work", {})
        image_ids = set(self.discover_continuation_images(record.capture_id))
        if isinstance(work.get("continuation_image_id"), str):
            image_ids.add(work["continuation_image_id"])
        for image_id in sorted(image_ids):
            self.runner.run(
                ["image", "rm", "-f", image_id], check=False, timeout_seconds=60
            )
        snapshot = work.get("snapshot_dir")
        if isinstance(snapshot, str):
            shutil.rmtree(snapshot, ignore_errors=True)

    def restore_archive(
        self,
        *,
        capture_id: str,
        arm: str,
        role: str,
        archive: dict[str, Any],
        target: str,
        continuation_image_id: str,
    ) -> None:
        helper = f"forge-checkpoint-{capture_id}-{arm}-{role}"
        snapshot_host = str(Path(archive["host_path"]).parent).replace("\\", "/")
        archive_name = Path(archive["host_path"]).name
        self.runner.run(
            [
                "run",
                "--rm",
                "--name",
                helper,
                "--label",
                f"{CAPTURE_LABEL}={capture_id}",
                "--label",
                f"{ROLE_LABEL}=restore-{arm}-{role}",
                "--mount",
                f"type=bind,src={snapshot_host},dst=/snapshot,readonly",
                "--mount",
                f"type=bind,src={target},dst=/target",
                continuation_image_id,
                "sh",
                "-c",
                f"tar --numeric-owner -xpf /snapshot/{archive_name} -C /target",
            ],
            timeout_seconds=120,
        )

    def cleanup_arm_helpers(self, capture_id: str, arm: str) -> None:
        for role in ("workspace", "artifacts"):
            self.runner.run(
                ["rm", "-f", f"forge-checkpoint-{capture_id}-{arm}-{role}"],
                check=False,
                timeout_seconds=20,
            )


def validate_arm_plan(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != set(ARMS):
        raise LifecycleGateError("arm plan does not contain exactly two arms")
    seen: dict[str, set[str]] = {
        field: set() for field in ("thread_id", "session_id", "environment_id")
    }
    compile_container_names: set[str] = set()
    for arm in ARMS:
        identity = value[arm]
        if not isinstance(identity, dict) or set(identity) != set(seen):
            raise LifecycleGateError(f"arm identity is invalid: {arm}")
        for field in seen:
            item = _identifier(identity[field], f"arm_plan.{arm}.{field}")
            if item in seen[field]:
                raise LifecycleGateError(f"arm {field} values must be unique")
            seen[field].add(item)
        container_name = (
            f"deerflow-compile-{identity['thread_id'][:8]}-{identity['session_id'][:8]}"
        )
        if container_name in compile_container_names:
            raise LifecycleGateError(
                "arm identities collide after CompileDockerRuntime truncation"
            )
        compile_container_names.add(container_name)
    return value


class RealLifecycleCheckpointGate:
    """按持久阶段组合 message、environment 和 budget capture。"""

    def __init__(
        self,
        *,
        coordinator: CaptureCoordinator,
        message_runtime: LifecycleMessageRuntime,
        environment: LifecycleEnvironmentAdapter,
        budget_capture: Callable[[str, str], dict[str, Any]],
        manager: Any | None = None,
        compile_runtime: Any | None = None,
        owner: str | None = None,
    ) -> None:
        self.coordinator = coordinator
        self.message_runtime = message_runtime
        self.environment = environment
        self.budget_capture = budget_capture
        self.manager = manager
        self.compile_runtime = compile_runtime
        self.owner = owner or f"coordinator-{uuid.uuid4().hex[:12]}"
        self.source_config: dict[str, Any] | None = None
        self.arms: dict[str, LifecycleArm] = {}

    @staticmethod
    def _combined_path(record: CaptureRecord) -> Path:
        work = record.payload.get("environment_work", {})
        snapshot = work.get("snapshot_dir")
        if not isinstance(snapshot, str):
            raise LifecycleGateError("capture snapshot directory is missing")
        return Path(snapshot) / "combined.json"

    def _freeze_budget(self, capture_id: str) -> CaptureRecord:
        record = self.coordinator.get(capture_id)
        message = record.payload["message"]
        manifest = budget_checkpoint.validate_manifest(
            self.budget_capture(capture_id, message["canonical_state_sha256"])
        )
        if manifest["checkpoint_id"] != capture_id:
            raise LifecycleGateError("budget checkpoint identity drifted")
        return self.coordinator.update(
            capture_id,
            self.owner,
            expected_phase="environment_frozen",
            target_phase="budget_frozen",
            patch={"budget": manifest},
        )

    def _publish(
        self, capture_id: str, *, crash_after_write: bool = False
    ) -> dict[str, Any]:
        record = self.coordinator.get(capture_id)
        if record.phase != "budget_frozen":
            raise LifecycleGateError(
                "combined manifest can only publish after budget freeze"
            )
        payload = record.payload
        environment_manifest = json.loads(
            Path(payload["environment"]["manifest_path"]).read_text(encoding="utf-8")
        )
        if environment_manifest.get("manifest_sha256") != manifest_payload_sha256(
            environment_manifest
        ):
            raise LifecycleGateError("environment manifest payload hash is invalid")
        if (
            environment_manifest["manifest_sha256"]
            != payload["environment"]["manifest_sha256"]
        ):
            raise LifecycleGateError(
                "environment manifest drifted before combined publication"
            )
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "manifest_sha256": "",
            "capture_id": capture_id,
            "capture_point": CAPTURE_POINT,
            "neutral": True,
            "parent": copy.deepcopy(payload["parent"]),
            "message": copy.deepcopy(payload["message"]),
            "evidence": copy.deepcopy(payload["evidence"]),
            "environment": copy.deepcopy(payload["environment"]),
            "budget": {
                "checkpoint_id": payload["budget"]["checkpoint_id"],
                "manifest_sha256": payload["budget"]["manifest_sha256"],
            },
            "arm_plan": copy.deepcopy(payload["arm_plan"]),
        }
        manifest["manifest_sha256"] = manifest_payload_sha256(manifest)
        path = self._combined_path(record)
        _atomic_write(path, canonical_bytes(manifest) + b"\n")
        if crash_after_write:
            raise SimulatedCrash("simulated crash after combined manifest write")
        self.coordinator.update(
            capture_id,
            self.owner,
            expected_phase="budget_frozen",
            target_phase="committed",
            patch={
                "combined": {
                    "manifest_path": str(path),
                    "manifest_sha256": manifest["manifest_sha256"],
                }
            },
        )
        return manifest

    def capture(
        self,
        *,
        capture_id: str,
        session: Any,
        instruction: str,
        arm_plan: dict[str, Any],
        bind_sources: dict[str, str],
        evidence: dict[str, Any] | Callable[[], dict[str, Any]],
        crash_after: str | None = None,
    ) -> dict[str, Any]:
        _safe_path_component(capture_id)
        validate_arm_plan(arm_plan)
        initial = {
            "parent": {
                "thread_id": session.thread_id,
                "session_id": session.session_id,
                "run_id": session.run_id,
                "submit_attempt_id": None,
            },
            "arm_plan": copy.deepcopy(arm_plan),
            "arms": {arm: {"status": "planned"} for arm in ARMS},
            "evidence": {},
        }
        self.coordinator.create(capture_id, initial)
        self.coordinator.acquire(capture_id, self.owner)
        try:
            record = self.coordinator.get(capture_id)
            if record.phase != "preparing":
                raise LifecycleGateError("capture id was already used")
            source_config, message = self.message_runtime.capture(
                capture_id=capture_id,
                session_id=session.session_id,
                instruction=instruction,
            )
            self.source_config = source_config
            resolved_evidence = (
                evidence() if callable(evidence) else copy.deepcopy(evidence)
            )
            if not isinstance(resolved_evidence.get("submit_attempt_id"), str):
                raise LifecycleGateError(
                    "capture evidence is missing submit_attempt_id"
                )
            self.coordinator.update(
                capture_id,
                self.owner,
                expected_phase="preparing",
                target_phase="message_frozen",
                patch={
                    "message": message,
                    "evidence": resolved_evidence,
                    "parent": {
                        "submit_attempt_id": resolved_evidence["submit_attempt_id"]
                    },
                },
            )
            if crash_after == "message_frozen":
                raise SimulatedCrash("simulated crash after message freeze")
            self.environment.capture(
                capture_id=capture_id,
                session=session,
                bind_sources=bind_sources,
                arm_plan=arm_plan,
                coordinator=self.coordinator,
                owner=self.owner,
                crash_after=crash_after,
            )
            self._freeze_budget(capture_id)
            if crash_after == "budget_frozen":
                raise SimulatedCrash("simulated crash after budget freeze")
            manifest = self._publish(
                capture_id,
                crash_after_write=crash_after == "combined_published",
            )
            return manifest
        finally:
            record = self.coordinator.get(capture_id)
            if record.lease_owner == self.owner:
                self.coordinator.release(capture_id, self.owner)

    def reconcile(self, capture_id: str) -> CaptureRecord:
        self.coordinator.acquire(capture_id, self.owner)
        try:
            record = self.coordinator.get(capture_id)
            self.environment.reconcile_parent(record)
            record = self.coordinator.get(capture_id)
            if record.phase in {"preparing", "message_frozen"}:
                manifest_path = (
                    Path(
                        record.payload.get("environment_work", {}).get(
                            "snapshot_dir", ""
                        )
                    )
                    / "environment.json"
                )
                if manifest_path.is_file():
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    if manifest.get("manifest_sha256") != manifest_payload_sha256(
                        manifest
                    ):
                        raise LifecycleGateError(
                            "recovered environment manifest hash is invalid"
                        )
                    record = self.coordinator.update(
                        capture_id,
                        self.owner,
                        expected_phase="message_frozen",
                        target_phase="environment_frozen",
                        patch={
                            "environment": {
                                "manifest_path": str(manifest_path),
                                "manifest_sha256": manifest["manifest_sha256"],
                                "continuation_image_id": manifest[
                                    "continuation_image_id"
                                ],
                            },
                            "environment_work": {"parent_paused": False},
                        },
                    )
                else:
                    self.environment.cleanup_partial(record)
                    record = self.coordinator.update(
                        capture_id,
                        self.owner,
                        expected_phase=record.phase,
                        target_phase="aborted",
                        last_error="incomplete environment capture was cleaned",
                    )
                    return self.coordinator.update(
                        capture_id,
                        self.owner,
                        expected_phase="aborted",
                        target_phase="cleaned",
                    )
            if record.phase == "environment_frozen":
                record = self._freeze_budget(capture_id)
            if record.phase == "budget_frozen":
                path = self._combined_path(record)
                if path.is_file():
                    manifest = json.loads(path.read_text(encoding="utf-8"))
                    if manifest.get("manifest_sha256") != manifest_payload_sha256(
                        manifest
                    ):
                        raise LifecycleGateError(
                            "recovered combined manifest hash is invalid"
                        )
                    record = self.coordinator.update(
                        capture_id,
                        self.owner,
                        expected_phase="budget_frozen",
                        target_phase="committed",
                        patch={
                            "combined": {
                                "manifest_path": str(path),
                                "manifest_sha256": manifest["manifest_sha256"],
                            }
                        },
                    )
                else:
                    self._publish(capture_id)
                    record = self.coordinator.get(capture_id)
            if record.phase == "committed" and self.manager is not None:
                for arm in ARMS:
                    arm_state = record.payload.get("arms", {}).get(arm, {})
                    if arm_state.get("status") == "provisioning":
                        self._cleanup_partial_arm(capture_id, arm, record)
                        record = self.coordinator.update(
                            capture_id,
                            self.owner,
                            patch={"arms": {arm: {"status": "planned"}}},
                        )
            return record
        finally:
            record = self.coordinator.get(capture_id)
            if record.lease_owner == self.owner:
                self.coordinator.release(capture_id, self.owner)

    def derive_message_arms(self, capture_id: str) -> dict[str, dict[str, Any]]:
        record = self.coordinator.get(capture_id)
        if record.phase != "committed":
            raise LifecycleGateError("only a committed capture can derive arms")
        source = self.source_config or self.message_runtime.config(
            record.payload["message"]["thread_id"]
        )
        return {
            arm: self.message_runtime.derive_arm(
                source,
                arm=arm,
                thread_id=record.payload["arm_plan"][arm]["thread_id"],
                session_id=record.payload["arm_plan"][arm]["session_id"],
            )
            for arm in ARMS
        }

    @staticmethod
    def _tree_manifest(root: Path) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        if not root.is_dir():
            return entries
        for path in sorted(
            root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()
        ):
            relative = path.relative_to(root).as_posix()
            stat = path.lstat()
            entry: dict[str, Any] = {
                "path": relative,
                "mode": stat.st_mode & 0o7777,
            }
            if path.is_symlink():
                entry.update(type="symlink", target=os.readlink(path))
            elif path.is_dir():
                entry["type"] = "directory"
            elif path.is_file():
                entry.update(type="file", size=stat.st_size, sha256=sha256_file(path))
            else:
                entry["type"] = "other"
            entries.append(entry)
        return entries

    def canonical_arm_environment(self, arm: str) -> dict[str, Any]:
        lifecycle_arm = self.arms[arm]
        session = lifecycle_arm.session
        return {
            "image_id": session.image_id,
            "workspace": self._tree_manifest(Path(session.leadagent_repo_dir).parent),
            "artifacts": self._tree_manifest(Path(session.leadagent_artifacts_dir)),
        }

    def _arm_host_targets(self, session: Any) -> dict[str, str]:
        from deerflow.compile.paths import (
            get_host_artifacts_dir,
            get_host_workspace_dir,
        )

        paths = self.manager.paths
        return {
            "workspace": get_host_workspace_dir(
                session.session_id, session.thread_id, paths
            ),
            "artifacts": get_host_artifacts_dir(
                session.session_id, session.thread_id, paths
            ),
        }

    @staticmethod
    def _copy_parent_state(parent: Any, arm_session: Any) -> None:
        if parent.replay_attempts:
            raise LifecycleGateError(
                "real lifecycle gate currently requires a pre-replay actionable failure"
            )
        for field_name in (
            "commit_sha",
            "build_system",
            "build_system_capabilities",
            "selected_build_system",
            "executed_build_system",
            "post_build_supporting_command_id",
            "post_build_started_at",
            "post_build_commands_remaining",
            "commands",
            "artifacts",
            "verification",
            "summary",
            "error",
        ):
            setattr(arm_session, field_name, copy.deepcopy(getattr(parent, field_name)))
        arm_session.status = parent.status
        arm_session.completed_at = None
        arm_session.finalized_at = None
        arm_session.termination_requested_at = None
        arm_session.termination_status = None
        arm_session.termination_error = None
        arm_session.container_id = None
        arm_session.container_name = None
        arm_session.image_id = None
        arm_session.replay_attempts = []

    def provision_arm(
        self,
        capture_id: str,
        arm: str,
        *,
        parent_session: Any,
        crash_after: str | None = None,
    ) -> LifecycleArm:
        if arm not in ARMS:
            raise LifecycleGateError("unknown arm")
        if self.manager is None or self.compile_runtime is None:
            raise LifecycleGateError(
                "arm provisioning requires Compile Session services"
            )
        self.coordinator.acquire(capture_id, self.owner)
        try:
            record = self.coordinator.get(capture_id)
            if record.phase != "committed":
                raise LifecycleGateError("only a committed capture can provision arms")
            arm_state = record.payload["arms"][arm]
            if arm_state.get("status") == "ready":
                session = self.manager.load_session(
                    record.payload["arm_plan"][arm]["session_id"],
                    record.payload["arm_plan"][arm]["thread_id"],
                )
                source = self.source_config or self.message_runtime.config(
                    record.payload["message"]["thread_id"]
                )
                message_config = self.message_runtime.config(
                    record.payload["arm_plan"][arm]["thread_id"]
                )
                if not self.message_runtime.graph.get_state(message_config).values:
                    message_config = self.message_runtime.derive_arm(
                        source,
                        arm=arm,
                        thread_id=session.thread_id,
                        session_id=session.session_id,
                    )
                lifecycle_arm = LifecycleArm(
                    arm=arm,
                    session=session,
                    message_config=message_config,
                    budget=budget_checkpoint.BudgetCheckpointRuntime(
                        record.payload["budget"], arm, budget_checkpoint.FakeClock()
                    ),
                )
                self.arms[arm] = lifecycle_arm
                return lifecycle_arm

            identity = record.payload["arm_plan"][arm]
            self.coordinator.update(
                capture_id,
                self.owner,
                patch={"arms": {arm: {"status": "provisioning"}}},
            )
            session = self.manager.create_session(
                thread_id=identity["thread_id"],
                session_id=identity["session_id"],
                run_id=f"{capture_id}-{arm}",
                repo_url=parent_session.repo_url,
                branch=parent_session.branch,
                image=record.payload["environment"]["continuation_image_id"],
            )
            self._copy_parent_state(parent_session, session)
            self.manager.save_session(session)
            if crash_after == "arm_session":
                raise SimulatedCrash(f"simulated crash after {arm} session creation")

            environment_manifest = json.loads(
                Path(record.payload["environment"]["manifest_path"]).read_text(
                    encoding="utf-8"
                )
            )
            targets = self._arm_host_targets(session)
            for role in ("workspace", "artifacts"):
                self.environment.restore_archive(
                    capture_id=capture_id,
                    arm=arm,
                    role=role,
                    archive=environment_manifest["archives"][role],
                    target=targets[role],
                    continuation_image_id=environment_manifest["continuation_image_id"],
                )
            self.compile_runtime.create_container(session)
            self.manager.save_session(session)
            if crash_after == "arm_container":
                raise SimulatedCrash(f"simulated crash after {arm} container creation")
            self.coordinator.update(
                capture_id,
                self.owner,
                patch={
                    "arms": {
                        arm: {
                            "status": "ready",
                            "thread_id": session.thread_id,
                            "session_id": session.session_id,
                            "container_id": session.container_id,
                            "container_name": session.container_name,
                            "image_id": session.image_id,
                        }
                    }
                },
            )

            source = self.source_config or self.message_runtime.config(
                record.payload["message"]["thread_id"]
            )
            message_config = self.message_runtime.derive_arm(
                source,
                arm=arm,
                thread_id=session.thread_id,
                session_id=session.session_id,
            )
            lifecycle_arm = LifecycleArm(
                arm=arm,
                session=session,
                message_config=message_config,
                budget=budget_checkpoint.BudgetCheckpointRuntime(
                    record.payload["budget"], arm, budget_checkpoint.FakeClock()
                ),
            )
            self.arms[arm] = lifecycle_arm
            return lifecycle_arm
        finally:
            record = self.coordinator.get(capture_id)
            if record.lease_owner == self.owner:
                self.coordinator.release(capture_id, self.owner)

    def _cleanup_partial_arm(
        self, capture_id: str, arm: str, record: CaptureRecord
    ) -> None:
        identity = record.payload["arm_plan"][arm]
        arm_state = record.payload.get("arms", {}).get(arm, {})
        container = arm_state.get("container_id") or arm_state.get("container_name")
        if not container:
            container = f"deerflow-compile-{identity['thread_id'][:8]}-{identity['session_id'][:8]}"
        self.environment.runner.run(
            ["rm", "-f", container], check=False, timeout_seconds=30
        )
        self.environment.cleanup_arm_helpers(capture_id, arm)
        try:
            session = self.manager.load_session(
                identity["session_id"], identity["thread_id"]
            )
        except (OSError, ValueError, json.JSONDecodeError):
            return
        shutil.rmtree(Path(session.metadata_path).parent, ignore_errors=True)

    def cleanup(self, capture_id: str, *, parent_session: Any) -> CaptureRecord:
        if self.manager is None or self.compile_runtime is None:
            raise LifecycleGateError(
                "checkpoint cleanup requires Compile Session services"
            )
        from deerflow.compile.operations import (
            cleanup_and_finalize_compile_session_impl,
        )

        self.coordinator.acquire(capture_id, self.owner)
        try:
            record = self.coordinator.get(capture_id)
            if record.phase == "committed":
                record = self.coordinator.update(
                    capture_id,
                    self.owner,
                    expected_phase="committed",
                    target_phase="cleanup_pending",
                )
            elif record.phase not in {"aborted", "cleanup_pending"}:
                raise LifecycleGateError(
                    f"capture cannot be cleaned from phase {record.phase}"
                )
            elif record.phase == "aborted":
                record = self.coordinator.update(
                    capture_id,
                    self.owner,
                    expected_phase="aborted",
                    target_phase="cleanup_pending",
                )

            for arm in ARMS:
                state = record.payload.get("arms", {}).get(arm, {})
                if state.get("status") != "ready":
                    self._cleanup_partial_arm(capture_id, arm, record)
                    continue
                session = self.manager.load_session(
                    record.payload["arm_plan"][arm]["session_id"],
                    record.payload["arm_plan"][arm]["thread_id"],
                )
                _updated, result = cleanup_and_finalize_compile_session_impl(
                    session=session,
                    interrupted_status="cancelled",
                    error="Real lifecycle checkpoint gate cleanup.",
                )
                if not result.succeeded:
                    raise LifecycleGateError(f"failed to clean {arm} Compile Session")

            parent, parent_result = cleanup_and_finalize_compile_session_impl(
                session=parent_session,
                interrupted_status="cancelled",
                error="Parent state was frozen by the real lifecycle checkpoint gate.",
            )
            if not parent_result.succeeded or parent.finalized_at is None:
                raise LifecycleGateError("failed to finalize parent Compile Session")

            work = record.payload.get("environment_work", {})
            image_id = work.get("continuation_image_id")
            if isinstance(image_id, str) and image_id:
                result = self.environment.runner.run(
                    ["image", "rm", "-f", image_id],
                    check=False,
                    timeout_seconds=60,
                )
                if result.returncode != 0:
                    raise LifecycleGateError("failed to remove continuation image")
            snapshot = work.get("snapshot_dir")
            if isinstance(snapshot, str):
                shutil.rmtree(snapshot, ignore_errors=True)
            record = self.coordinator.update(
                capture_id,
                self.owner,
                expected_phase="cleanup_pending",
                target_phase="cleaned",
                patch={"cleanup": {"succeeded": True}},
            )
            return record
        except Exception as exc:
            record = self.coordinator.get(capture_id)
            if (
                record.phase != "cleanup_pending"
                and "cleanup_pending" in TRANSITIONS[record.phase]
            ):
                self.coordinator.update(
                    capture_id,
                    self.owner,
                    expected_phase=record.phase,
                    target_phase="cleanup_pending",
                    last_error=str(exc),
                )
            raise
        finally:
            record = self.coordinator.get(capture_id)
            if record.lease_owner == self.owner:
                self.coordinator.release(capture_id, self.owner)

    def external_counts(self) -> dict[str, int]:
        return {
            "provider_calls": 0,
            "formal_physical_attempts": 0,
            "model_tokens": 0,
        }
