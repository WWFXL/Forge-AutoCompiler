#!/usr/bin/env python3
"""验证 verifier failure checkpoint 分支语义的非模型原型。"""

from __future__ import annotations

import copy
import hashlib
import json
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

FIXTURE_SCHEMA_VERSION = "forge-failure-checkpoint-fixture-1.0.0"
BASELINE_ARM = "baseline"
TREATMENT_ARM = "treatment"
ALLOWED_ARMS = frozenset({BASELINE_ARM, TREATMENT_ARM})
CONTINUATION_NODE = "continue_model"


class FailureCheckpointPrototypeError(ValueError):
    pass


class FailureCheckpointState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    fixture_id: str
    arm: str
    session_id: str


@dataclass
class PrototypeCounters:
    submit_calls: int = 0
    fake_model_calls: int = 0
    provider_calls: int = 0
    docker_calls: int = 0
    physical_attempts: int = 0


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def fixture_payload_sha256(fixture: dict[str, Any]) -> str:
    payload = {key: value for key, value in fixture.items() if key != "fixture_sha256"}
    return sha256(canonical_bytes(payload))


def _require_exact_fields(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise FailureCheckpointPrototypeError(f"{label} fields do not match the frozen schema")
    return value


def validate_fixture(fixture: Any) -> dict[str, Any]:
    fixture = _require_exact_fields(
        fixture,
        {
            "schema_version",
            "fixture_id",
            "fixture_sha256",
            "read_only",
            "instruction",
            "source",
            "session",
            "neutral_feedback",
            "repair_packet",
        },
        "fixture",
    )
    if fixture["schema_version"] != FIXTURE_SCHEMA_VERSION:
        raise FailureCheckpointPrototypeError("fixture schema version is invalid")
    if fixture["read_only"] is not True:
        raise FailureCheckpointPrototypeError("fixture must be marked read-only")
    if not isinstance(fixture["fixture_id"], str) or not fixture["fixture_id"].startswith("slot-"):
        raise FailureCheckpointPrototypeError("fixture identity is invalid")
    if not isinstance(fixture["instruction"], str) or not fixture["instruction"]:
        raise FailureCheckpointPrototypeError("fixture instruction is invalid")

    source = _require_exact_fields(
        fixture["source"],
        {
            "benchmark_id",
            "manifest_sha256",
            "slot_order",
            "case_id",
            "source_event_sequence",
            "source_feedback_sha256",
            "evidence_scope",
            "model_transcript_available",
        },
        "fixture source",
    )
    if source["evidence_scope"] != "sanitized_contract_only" or source["model_transcript_available"] is not False:
        raise FailureCheckpointPrototypeError("fixture source scope is invalid")

    session = _require_exact_fields(
        fixture["session"],
        {"session_alias", "build_system", "command_cutoff", "artifacts"},
        "fixture session",
    )
    if not isinstance(session["session_alias"], str) or not session["session_alias"].startswith("fixture-"):
        raise FailureCheckpointPrototypeError("fixture session alias is invalid")

    feedback = _require_exact_fields(
        fixture["neutral_feedback"],
        {
            "status",
            "actionable",
            "evidence_complete",
            "primary_classification",
            "submit_attempt_alias",
            "supporting_command_alias",
        },
        "neutral feedback",
    )
    if feedback["status"] != "failed" or feedback["actionable"] is not True or feedback["evidence_complete"] is not True:
        raise FailureCheckpointPrototypeError("neutral feedback is not actionable")
    if "repair_packet" in feedback:
        raise FailureCheckpointPrototypeError("neutral feedback must not contain treatment data")
    if fixture["repair_packet"].get("primary_classification") != feedback["primary_classification"]:
        raise FailureCheckpointPrototypeError("repair packet classification drifted")

    digest = fixture_payload_sha256(fixture)
    if fixture["fixture_sha256"] != digest:
        raise FailureCheckpointPrototypeError("fixture SHA-256 does not match canonical payload")
    return fixture


def load_fixture(path: Path) -> dict[str, Any]:
    return validate_fixture(json.loads(path.read_text(encoding="utf-8")))


class DeterministicFakeModel:
    def __init__(self, counters: PrototypeCounters):
        self._counters = counters

    def invoke(self, _messages: list[BaseMessage]) -> AIMessage:
        self._counters.fake_model_calls += 1
        return AIMessage(
            content="deterministic checkpoint continuation completed",
            id="fixture-continuation-response",
        )


class FailureCheckpointPrototype:
    def __init__(self, fixture: dict[str, Any], checkpointer: Any, counters: PrototypeCounters):
        self.fixture = copy.deepcopy(validate_fixture(fixture))
        self.counters = counters
        self.fake_model = DeterministicFakeModel(counters)
        self.graph = self._build_graph(checkpointer)

    def _build_graph(self, checkpointer: Any):
        graph = StateGraph(FailureCheckpointState)
        graph.add_node("request_submit", self._request_submit)
        graph.add_node("submit_failure", self._submit_failure)
        graph.add_node(CONTINUATION_NODE, self._continue_model)
        graph.add_edge(START, "request_submit")
        graph.add_edge("request_submit", "submit_failure")
        graph.add_edge("submit_failure", CONTINUATION_NODE)
        graph.add_edge(CONTINUATION_NODE, END)
        return graph.compile(
            checkpointer=checkpointer,
            interrupt_before=[CONTINUATION_NODE],
        )

    def _request_submit(self, _state: FailureCheckpointState) -> dict[str, list[AIMessage]]:
        return {
            "messages": [
                AIMessage(
                    content="",
                    id="fixture-submit-request",
                    tool_calls=[
                        {
                            "name": "submit_build_result",
                            "args": {},
                            "id": "fixture-submit-call",
                            "type": "tool_call",
                        }
                    ],
                )
            ]
        }

    def _submit_failure(self, state: FailureCheckpointState) -> dict[str, list[ToolMessage]]:
        self.counters.submit_calls += 1
        request = state["messages"][-1]
        if not isinstance(request, AIMessage) or not request.tool_calls:
            raise FailureCheckpointPrototypeError("submit request is missing")
        return {
            "messages": [
                ToolMessage(
                    content=canonical_bytes(self.fixture["neutral_feedback"]).decode("utf-8"),
                    id="fixture-submit-feedback",
                    name="submit_build_result",
                    tool_call_id=request.tool_calls[0]["id"],
                )
            ]
        }

    def _continue_model(self, state: FailureCheckpointState) -> dict[str, list[AIMessage]]:
        return {"messages": [self.fake_model.invoke(state["messages"])]}

    @staticmethod
    def config(thread_id: str) -> dict[str, dict[str, str]]:
        return {"configurable": {"thread_id": thread_id}}

    def capture(self, thread_id: str) -> dict[str, Any]:
        config = self.config(thread_id)
        self.graph.invoke(
            {
                "messages": [
                    HumanMessage(
                        content=self.fixture["instruction"],
                        id="fixture-human-instruction",
                    )
                ],
                "fixture_id": self.fixture["fixture_id"],
                "arm": "neutral",
                "session_id": self.fixture["session"]["session_alias"],
            },
            config,
        )
        snapshot = self.graph.get_state(config)
        if tuple(snapshot.next) != (CONTINUATION_NODE,):
            raise FailureCheckpointPrototypeError("graph did not pause before continuation")
        return config

    def derive_arm(
        self,
        source_config: dict[str, Any],
        *,
        arm: str,
        session_id: str,
        thread_id: str,
    ) -> dict[str, Any]:
        if arm not in ALLOWED_ARMS:
            raise FailureCheckpointPrototypeError("checkpoint arm is invalid")
        source = self.graph.get_state(source_config)
        if tuple(source.next) != (CONTINUATION_NODE,):
            raise FailureCheckpointPrototypeError("source checkpoint is not resumable")
        values = copy.deepcopy(source.values)
        messages = list(values["messages"])
        feedback = messages[-1]
        if not isinstance(feedback, ToolMessage):
            raise FailureCheckpointPrototypeError("source checkpoint feedback is missing")
        content = copy.deepcopy(self.fixture["neutral_feedback"])
        if arm == TREATMENT_ARM:
            content["repair_packet"] = copy.deepcopy(self.fixture["repair_packet"])
        messages[-1] = ToolMessage(
            content=canonical_bytes(content).decode("utf-8"),
            id=feedback.id,
            name=feedback.name,
            tool_call_id=feedback.tool_call_id,
            status=feedback.status,
        )
        values.update(messages=messages, arm=arm, session_id=session_id)
        target_config = self.config(thread_id)
        self.graph.update_state(target_config, values, as_node="submit_failure")
        target = self.graph.get_state(target_config)
        if tuple(target.next) != (CONTINUATION_NODE,):
            raise FailureCheckpointPrototypeError("derived checkpoint cannot resume at continuation")
        return target_config

    def resume(self, config: dict[str, Any]) -> dict[str, Any]:
        self.graph.invoke(None, config)
        return self.graph.get_state(config).values


def serialize_checkpoint_state(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "fixture_id": state["fixture_id"],
        "arm": state["arm"],
        "session_id": state["session_id"],
        "messages": [message_to_dict(message) for message in state["messages"]],
    }


def canonical_state_for_pairing(state: dict[str, Any]) -> dict[str, Any]:
    canonical = serialize_checkpoint_state(state)
    canonical["arm"] = "<arm>"
    canonical["session_id"] = "<session>"
    for message in canonical["messages"]:
        if message["type"] == "tool" and message["data"].get("name") == "submit_build_result":
            message["data"]["content"] = "<feedback>"
    return canonical


def state_difference_paths(left: dict[str, Any], right: dict[str, Any]) -> set[str]:
    differences: set[str] = set()

    def walk(a: Any, b: Any, path: str) -> None:
        if type(a) is not type(b):
            differences.add(path)
            return
        if isinstance(a, dict):
            for key in sorted(set(a) | set(b)):
                child = f"{path}.{key}" if path else key
                if key not in a or key not in b:
                    differences.add(child)
                else:
                    walk(a[key], b[key], child)
            return
        if isinstance(a, list):
            if len(a) != len(b):
                differences.add(f"{path}.length")
            for index, (a_item, b_item) in enumerate(zip(a, b, strict=False)):
                walk(a_item, b_item, f"{path}[{index}]")
            return
        if a != b:
            differences.add(path)

    walk(serialize_checkpoint_state(left), serialize_checkpoint_state(right), "")
    return differences
