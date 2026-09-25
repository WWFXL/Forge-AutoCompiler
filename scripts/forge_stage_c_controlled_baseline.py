#!/usr/bin/env python3
"""Stage C 的 CXXCrafter-style 受控基线 adapter。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

SCHEMA_VERSION = "forge-stage-c-controlled-baseline-1.0.0"
_IMAGE_ID = re.compile(r"^sha256:[0-9a-f]{64}$")


class ControlledBaselineError(RuntimeError):
    """受控基线合同、预算、候选或执行证据无效。"""


class ControlledBaselineBudgetExceeded(ControlledBaselineError):
    """受控基线达到共享请求、token 或墙钟上限。"""


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _write_once(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())


@dataclass(frozen=True)
class ControlledBaselineLimits:
    max_model_requests: int
    max_recorded_tokens: int
    work_timeout_seconds: int

    def validate(self) -> None:
        if self.max_model_requests < 1 or self.max_recorded_tokens < 1:
            raise ControlledBaselineError("请求与 token 上限必须为正数")
        if self.work_timeout_seconds < 1:
            raise ControlledBaselineError("work timeout 必须为正数")


@dataclass(frozen=True)
class ControlledBuildResult:
    execution_id: str
    dockerfile_sha256: str
    succeeded: bool
    timed_out: bool
    exit_code: int | None
    duration_seconds: float
    output_tail: str
    artifact_paths: tuple[str, ...]
    artifact_manifest_sha256: str | None
    candidate_image_id: str | None

    def validate(self) -> None:
        if not self.execution_id or len(self.output_tail.encode()) > 64 * 1024:
            raise ControlledBaselineError("executor result identity 或输出边界无效")
        if not re.fullmatch(r"[0-9a-f]{64}", self.dockerfile_sha256):
            raise ControlledBaselineError("executor Dockerfile SHA-256 无效")
        if self.succeeded and (
            self.timed_out
            or self.exit_code != 0
            or not self.artifact_paths
            or self.artifact_manifest_sha256 is None
            or self.candidate_image_id is None
        ):
            raise ControlledBaselineError("成功 executor result 未闭合")


class ControlledBuildExecutor(Protocol):
    def execute(self, dockerfile: str, *, revision: int) -> ControlledBuildResult: ...


@dataclass(frozen=True)
class ControlledBaselineCandidate:
    schema_version: str
    candidate_id: str
    task_id: str
    attempt_id: str
    method: str
    kind: str
    base_image_id: str
    dockerfile_sha256: str
    artifact_paths: tuple[str, ...]
    artifact_manifest_sha256: str
    executor_candidate_image_id: str
    revision: int

    def validate(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ControlledBaselineError("candidate schema_version 无效")
        if self.method != "cxxcrafter-controlled" or self.kind != "dockerfile":
            raise ControlledBaselineError("candidate 方法身份无效")
        if _IMAGE_ID.fullmatch(self.base_image_id) is None:
            raise ControlledBaselineError("candidate base image ID 无效")
        if not self.artifact_paths or len(set(self.artifact_paths)) != len(
            self.artifact_paths
        ):
            raise ControlledBaselineError("candidate artifact paths 无效")
        for value in (self.dockerfile_sha256, self.artifact_manifest_sha256):
            if re.fullmatch(r"[0-9a-f]{64}", value) is None:
                raise ControlledBaselineError("candidate SHA-256 无效")


@dataclass(frozen=True)
class ControlledBaselineOutcome:
    task_id: str
    attempt_id: str
    candidate_generated: bool
    candidate_submitted: bool
    termination_reason: str
    model_requests: int
    recorded_tokens: int
    executor_runs: int
    judge_runs: int
    modifier_runs: int
    duration_seconds: float
    candidate: ControlledBaselineCandidate | None
    evidence_head_sha256: str


class EvidenceLedger:
    def __init__(self, path: Path, *, task_id: str, attempt_id: str):
        self.path = path
        self.task_id = task_id
        self.attempt_id = attempt_id
        self.sequence = 0
        self.head_sha256 = "0" * 64
        _write_once(path, "")

    def append(self, event_type: str, **payload: Any) -> None:
        self.sequence += 1
        value = {
            "schema_version": SCHEMA_VERSION,
            "event_id": f"event:{uuid.uuid4().hex}",
            "sequence": self.sequence,
            "task_id": self.task_id,
            "attempt_id": self.attempt_id,
            "event_type": event_type,
            "payload": payload,
            "previous_hash": self.head_sha256,
        }
        event_hash = canonical_sha256(value)
        value["event_hash"] = event_hash
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(canonical_json(value) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        self.head_sha256 = event_hash


class RequestBudget:
    def __init__(self, limits: ControlledBaselineLimits, started: float):
        limits.validate()
        self.limits = limits
        self.started = started
        self.requests = 0
        self.tokens = 0

    def before_request(self) -> None:
        self._check_time()
        if self.requests >= self.limits.max_model_requests:
            raise ControlledBaselineBudgetExceeded("model_requests")
        self.requests += 1

    def after_request(self, tokens: int) -> None:
        if tokens < 0:
            raise ControlledBaselineError("recorded tokens 不能为负数")
        self.tokens += tokens
        if self.tokens > self.limits.max_recorded_tokens:
            raise ControlledBaselineBudgetExceeded("recorded_tokens")
        self._check_time()

    def _check_time(self) -> None:
        if time.monotonic() - self.started > self.limits.work_timeout_seconds:
            raise ControlledBaselineBudgetExceeded("work_timeout")


def _response_text(response: Any) -> str:
    content = getattr(response, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            item if isinstance(item, str) else str(item.get("text", ""))
            for item in content
            if isinstance(item, (str, dict))
        )
    if isinstance(response, str):
        return response
    return ""


def _response_tokens(response: Any) -> int:
    usage = getattr(response, "usage_metadata", None)
    if isinstance(usage, dict):
        value = usage.get("total_tokens", 0)
        if isinstance(value, int) and value >= 0:
            return value
    metadata = getattr(response, "response_metadata", None)
    if isinstance(metadata, dict):
        token_usage = metadata.get("token_usage", metadata.get("usage", {}))
        if isinstance(token_usage, dict):
            value = token_usage.get("total_tokens", 0)
            if isinstance(value, int) and value >= 0:
                return value
    return 0


def _parse_object(text: str, label: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```json") and stripped.endswith("```"):
        stripped = stripped[7:-3].strip()
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ControlledBaselineError(f"{label} 未返回单一 JSON 对象") from exc
    if not isinstance(value, dict):
        raise ControlledBaselineError(f"{label} 必须返回 JSON 对象")
    return value


def validate_dockerfile(dockerfile: str, base_image_id: str) -> str:
    if _IMAGE_ID.fullmatch(base_image_id) is None:
        raise ControlledBaselineError("冻结 base image ID 无效")
    if not isinstance(dockerfile, str) or not dockerfile.strip():
        raise ControlledBaselineError("Dockerfile 为空")
    if len(dockerfile.encode()) > 128 * 1024 or "\0" in dockerfile:
        raise ControlledBaselineError("Dockerfile 超过体积边界或包含 NUL")
    instructions = [
        line.strip()
        for line in dockerfile.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    from_lines = [line for line in instructions if line.upper().startswith("FROM ")]
    if from_lines != [f"FROM {base_image_id}"]:
        raise ControlledBaselineError("Dockerfile 必须且只能 FROM 冻结完整 image ID")
    normalized = dockerfile.lower()
    forbidden = (
        "apt-get",
        "apt install",
        "apt upgrade",
        "curl ",
        "wget ",
        "git clone",
        "git fetch",
        "--privileged",
        "/var/run/docker.sock",
        "http://",
        "https://",
    )
    if any(token in normalized for token in forbidden):
        raise ControlledBaselineError("Dockerfile 包含禁用的网络、依赖或特权动作")
    if not any(line.upper().startswith("COPY SOURCE/") for line in instructions):
        raise ControlledBaselineError("Dockerfile 必须从固定 context 复制 source/")
    if "/artifacts" not in dockerfile:
        raise ControlledBaselineError("Dockerfile 未形成统一 /artifacts 候选")
    return dockerfile.rstrip() + "\n"


class ControlledBaselineRunner:
    def __init__(
        self,
        *,
        task_contract: dict[str, Any],
        source_observation: dict[str, Any],
        task_id: str,
        attempt_id: str,
        base_image_id: str,
        model: Any,
        executor: ControlledBuildExecutor,
        limits: ControlledBaselineLimits,
        output_dir: Path,
        clock: Any = time.monotonic,
    ):
        self.task_contract = task_contract
        self.source_observation = source_observation
        self.task_id = task_id
        self.attempt_id = attempt_id
        self.base_image_id = base_image_id
        self.model = model
        self.executor = executor
        self.limits = limits
        self.output_dir = output_dir
        self.clock = clock

    def _invoke(
        self,
        budget: RequestBudget,
        ledger: EvidenceLedger,
        role: str,
        prompt: str,
    ) -> dict[str, Any]:
        budget.before_request()
        ledger.append(
            "model.request_started", role=role, request_sequence=budget.requests
        )
        try:
            response = self.model.invoke(prompt)
        except Exception as exc:
            ledger.append(
                "model.request_failed",
                role=role,
                request_sequence=budget.requests,
                error_class=type(exc).__name__,
            )
            raise
        tokens = _response_tokens(response)
        budget.after_request(tokens)
        ledger.append(
            "model.request_completed",
            role=role,
            request_sequence=budget.requests,
            recorded_tokens=tokens,
        )
        return _parse_object(_response_text(response), role)

    def run(self) -> ControlledBaselineOutcome:
        started = self.clock()
        budget = RequestBudget(self.limits, started)
        self.output_dir.mkdir(parents=True, exist_ok=False)
        ledger = EvidenceLedger(
            self.output_dir / "events.jsonl",
            task_id=self.task_id,
            attempt_id=self.attempt_id,
        )
        executor_runs = 0
        judge_runs = 0
        modifier_runs = 0
        candidate_generated = False
        candidate: ControlledBaselineCandidate | None = None
        termination = "method_failed"
        try:
            parser_value = self._invoke(
                budget,
                ledger,
                "parser",
                canonical_json(
                    {
                        "instruction": "分析冻结源码观察，只返回 build_system、dependencies、build_steps、artifact_steps 四字段 JSON。",
                        "task_contract": self.task_contract,
                        "source_observation": self.source_observation,
                    }
                ),
            )
            if set(parser_value) != {
                "build_system",
                "dependencies",
                "build_steps",
                "artifact_steps",
            }:
                raise ControlledBaselineError("parser JSON 字段无效")
            generated = self._invoke(
                budget,
                ledger,
                "generator",
                canonical_json(
                    {
                        "instruction": (
                            '只返回 {"dockerfile": string}。Dockerfile 必须 FROM 给定完整 image ID，'
                            "COPY source/ 到 /workspace/repo，不得联网或安装依赖，并把精确交付写入 /artifacts。"
                        ),
                        "base_image_id": self.base_image_id,
                        "task_contract": self.task_contract,
                        "parsed_build": parser_value,
                    }
                ),
            )
            dockerfile = validate_dockerfile(
                str(generated.get("dockerfile", "")), self.base_image_id
            )
            candidate_generated = True
            revision = 1
            while True:
                budget._check_time()
                ledger.append(
                    "executor.started",
                    revision=revision,
                    dockerfile_sha256=hashlib.sha256(dockerfile.encode()).hexdigest(),
                )
                execution = self.executor.execute(dockerfile, revision=revision)
                execution.validate()
                executor_runs += 1
                ledger.append("executor.completed", **asdict(execution))
                judge = self._invoke(
                    budget,
                    ledger,
                    "judge",
                    canonical_json(
                        {
                            "instruction": '只返回 {"success": boolean, "advice": string|null}。仅根据 Dockerfile 和 executor 证据判断内部控制流。',
                            "task_contract": self.task_contract,
                            "dockerfile": dockerfile,
                            "executor": asdict(execution),
                        }
                    ),
                )
                judge_runs += 1
                if (
                    set(judge) != {"success", "advice"}
                    or type(judge["success"]) is not bool
                ):
                    raise ControlledBaselineError("judge JSON 字段无效")
                if judge["success"] and execution.succeeded:
                    candidate = ControlledBaselineCandidate(
                        schema_version=SCHEMA_VERSION,
                        candidate_id=f"candidate:{uuid.uuid4().hex}",
                        task_id=self.task_id,
                        attempt_id=self.attempt_id,
                        method="cxxcrafter-controlled",
                        kind="dockerfile",
                        base_image_id=self.base_image_id,
                        dockerfile_sha256=execution.dockerfile_sha256,
                        artifact_paths=execution.artifact_paths,
                        artifact_manifest_sha256=execution.artifact_manifest_sha256
                        or "",
                        executor_candidate_image_id=execution.candidate_image_id or "",
                        revision=revision,
                    )
                    candidate.validate()
                    _write_once(
                        self.output_dir / "Dockerfile",
                        dockerfile,
                    )
                    _write_once(
                        self.output_dir / "candidate.json",
                        canonical_json(asdict(candidate)) + "\n",
                    )
                    ledger.append(
                        "candidate.submitted",
                        candidate_id=candidate.candidate_id,
                        candidate_sha256=canonical_sha256(asdict(candidate)),
                    )
                    termination = "candidate_submitted"
                    break
                modified = self._invoke(
                    budget,
                    ledger,
                    "modifier",
                    canonical_json(
                        {
                            "instruction": '只返回 {"dockerfile": string}，根据内部 Judge 建议最小修改完整 Dockerfile。',
                            "base_image_id": self.base_image_id,
                            "task_contract": self.task_contract,
                            "dockerfile": dockerfile,
                            "executor": asdict(execution),
                            "judge_advice": judge["advice"],
                        }
                    ),
                )
                modifier_runs += 1
                dockerfile = validate_dockerfile(
                    str(modified.get("dockerfile", "")), self.base_image_id
                )
                revision += 1
        except ControlledBaselineBudgetExceeded as exc:
            termination = f"budget_exhausted:{exc}"
            ledger.append("method.terminated", reason=termination)
        except Exception as exc:
            termination = f"method_error:{type(exc).__name__}"
            ledger.append("method.terminated", reason=termination)
        outcome = ControlledBaselineOutcome(
            task_id=self.task_id,
            attempt_id=self.attempt_id,
            candidate_generated=candidate_generated,
            candidate_submitted=candidate is not None,
            termination_reason=termination,
            model_requests=budget.requests,
            recorded_tokens=budget.tokens,
            executor_runs=executor_runs,
            judge_runs=judge_runs,
            modifier_runs=modifier_runs,
            duration_seconds=round(self.clock() - started, 6),
            candidate=candidate,
            evidence_head_sha256=ledger.head_sha256,
        )
        _write_once(
            self.output_dir / "outcome.json",
            canonical_json(
                {
                    **asdict(outcome),
                    "candidate": asdict(candidate) if candidate is not None else None,
                }
            )
            + "\n",
        )
        return outcome
