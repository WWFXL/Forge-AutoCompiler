#!/usr/bin/env python3
"""Validate and render the result-blind per-case formal build protocol."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROTOCOL = (
    REPO_ROOT / "benchmarks" / "preregistrations" / "cpp-formal-v1-cases.json"
)
DEFAULT_PREREGISTRATION = (
    REPO_ROOT / "benchmarks" / "preregistrations" / "cpp-formal-v1.json"
)
DEFAULT_MARKDOWN = (
    REPO_ROOT / "benchmarks" / "preregistrations" / "cpp-formal-v1-cases.md"
)

IDENTIFIER_RE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PACKAGE_RE = re.compile(r"^[a-z0-9][a-z0-9+.-]*$")
TARGET_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:+/-]*$")
SECRET_RE = re.compile(
    r"(?:sk-[A-Za-z0-9_-]{12,}|authorization\s*:|api[_-]?key\s*[=:])",
    re.IGNORECASE,
)
PLACEHOLDER_RE = re.compile(r"(?:\bTODO\b|\bTBD\b|pending|placeholder)", re.IGNORECASE)
BUILD_SYSTEMS = ("cmake", "make", "autotools")
ARTIFACT_TYPES = ("executable", "shared_library", "static_library", "object")
OSS_FUZZ_COMMIT = "08682bfc14e31d12fcc94b52b4805d7994fb70fd"


class CaseProtocolError(ValueError):
    """Raised when the per-case protocol is incomplete or inconsistent."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CaseProtocolError(f"Cannot load {label}: {path}") from exc
    if not isinstance(value, dict):
        raise CaseProtocolError(f"{label} root must be an object")
    return value


def load_protocol(path: Path = DEFAULT_PROTOCOL) -> dict[str, Any]:
    return _load_object(path, "case protocol")


def load_preregistration(path: Path = DEFAULT_PREREGISTRATION) -> dict[str, Any]:
    return _load_object(path, "preregistration")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CaseProtocolError(message)


def _iter_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _iter_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_strings(item)


def _validate_relative_path(
    value: str, *, label: str, filename_only: bool = False
) -> None:
    path = PurePosixPath(value)
    _require(bool(value) and "\\" not in value, f"{label} must be a POSIX path")
    _require(not path.is_absolute(), f"{label} must be relative")
    _require(".." not in path.parts and "." not in path.parts, f"{label} is unsafe")
    _require(not any(char in value for char in "*?[]{}"), f"{label} cannot use globs")
    _require(not filename_only or len(path.parts) == 1, f"{label} must be a filename")


def _validate_evidence_url(
    value: str,
    *,
    repository_url: str,
    commit: str,
    evidence_path: str,
    evidence_kind: str,
) -> None:
    parsed = urlsplit(value)
    _require(
        parsed.scheme == "https"
        and parsed.hostname == "github.com"
        and not parsed.username
        and not parsed.password
        and not parsed.query
        and not parsed.fragment,
        f"Unsafe evidence URL: {value}",
    )
    if evidence_kind == "upstream_exact_commit":
        expected_prefix = f"{repository_url}/blob/{commit}/"
        _require(
            value == expected_prefix + evidence_path,
            "Upstream evidence is not exact-commit pinned",
        )
    else:
        expected = (
            "https://github.com/google/oss-fuzz/blob/"
            f"{OSS_FUZZ_COMMIT}/projects/{evidence_path}"
        )
        _require(value == expected, "OSS-Fuzz evidence is not snapshot pinned")


def validate_protocol(
    protocol: dict[str, Any],
    preregistration: dict[str, Any],
) -> dict[str, Any]:
    _require(protocol.get("schema_version") == "1.0.0", "Unexpected schema_version")
    _require(
        protocol.get("document_type") == "formal-case-protocol",
        "Unexpected document_type",
    )
    metadata = protocol["protocolization"]
    _require(
        metadata["id"] == "forge-cpp-formal-v1-cases",
        "Unexpected protocolization ID",
    )
    _require(metadata["issue"] == 78, "Unexpected protocolization Issue")
    _require(
        metadata["audit_mode"] == "result-blind-static-document-review",
        "Audit mode drifted",
    )
    _require(
        metadata["collection_authorized"] is False,
        "Case protocol must not authorize collection",
    )
    _require(
        metadata["base_preregistration_id"] == preregistration["preregistration"]["id"],
        "Base preregistration ID drifted",
    )
    preregistration_digest = canonical_sha256(preregistration)
    _require(
        metadata["base_preregistration_sha256"] == preregistration_digest,
        "Base preregistration digest drifted",
    )
    _require(
        metadata["oss_fuzz_snapshot_commit"] == OSS_FUZZ_COMMIT,
        "OSS-Fuzz snapshot drifted",
    )

    for text in _iter_strings(protocol):
        _require(not SECRET_RE.search(text), "Secret-like content is forbidden")
        _require(
            not PLACEHOLDER_RE.search(text),
            "Pending or placeholder content is forbidden",
        )

    prereg_cases = {case["id"]: case for case in preregistration["cases"]}
    cases = protocol["cases"]
    _require(len(cases) == len(prereg_cases) == 30, "Exactly 30 cases are required")
    _require(
        {case["id"] for case in cases} == set(prereg_cases),
        "Case set differs from the preregistration",
    )

    strata: Counter[str] = Counter()
    artifact_names: list[str] = []
    evidence_urls: set[str] = set()
    for case in cases:
        case_id = case["id"]
        _require(
            IDENTIFIER_RE.fullmatch(case_id) is not None, f"Bad case ID: {case_id}"
        )
        base = prereg_cases[case_id]
        for field in ("repository_url", "commit", "build_system"):
            _require(case[field] == base[field], f"{case_id} {field} drifted")
        _require(
            case["build_system"] in BUILD_SYSTEMS, f"{case_id} has bad build system"
        )
        _require(
            COMMIT_RE.fullmatch(case["commit"]) is not None, f"{case_id} has bad commit"
        )
        _require(case["review_state"] == "reviewed", f"{case_id} is not reviewed")
        _require(
            case["result_data_consulted"] is False, f"{case_id} is not result blind"
        )

        recipe = case["recipe"]
        _validate_relative_path(
            recipe["source_subdir"], label=f"{case_id} source_subdir"
        )
        _require(
            recipe["source_subdir"] == "."
            or not recipe["source_subdir"].startswith("."),
            f"{case_id} source_subdir is hidden",
        )
        _require(
            isinstance(recipe["bootstrap_commands"], list)
            and all(
                isinstance(command, str) and command
                for command in recipe["bootstrap_commands"]
            ),
            f"{case_id} has bad bootstrap commands",
        )
        _require(
            isinstance(recipe["configure_arguments"], list)
            and all(
                isinstance(argument, str) and argument
                for argument in recipe["configure_arguments"]
            ),
            f"{case_id} has bad configure arguments",
        )
        targets = recipe["build_targets"]
        _require(
            isinstance(targets, list)
            and targets
            and all(TARGET_RE.fullmatch(target) for target in targets),
            f"{case_id} has bad build targets",
        )
        packages = recipe["required_system_packages"]
        _require(
            isinstance(packages, list)
            and packages
            and len(packages) == len(set(packages))
            and all(PACKAGE_RE.fullmatch(package) for package in packages),
            f"{case_id} has bad system packages",
        )

        artifacts = case["artifact_oracle"]["required_artifacts"]
        _require(
            isinstance(artifacts, list) and artifacts,
            f"{case_id} has no artifact oracle",
        )
        staged_names: set[str] = set()
        for artifact in artifacts:
            _validate_relative_path(
                artifact["staged_relative_path"],
                label=f"{case_id} staged artifact",
                filename_only=True,
            )
            _validate_relative_path(
                artifact["build_output_path"],
                label=f"{case_id} build output",
            )
            _require(
                artifact["artifact_type"] in ARTIFACT_TYPES,
                f"{case_id} has unsupported artifact type",
            )
            _require(
                artifact["producing_target"] in targets,
                f"{case_id} artifact target is not built",
            )
            _require(
                artifact["staged_relative_path"] not in staged_names,
                f"{case_id} has duplicate staged artifacts",
            )
            staged_names.add(artifact["staged_relative_path"])
            artifact_names.append(artifact["staged_relative_path"])

        evidence = case["evidence"]
        _require(len(evidence) >= 1, f"{case_id} has no evidence")
        covered_claims: set[str] = set()
        for item in evidence:
            _require(
                item["kind"] in ("upstream_exact_commit", "oss_fuzz_snapshot"),
                f"{case_id} has unsupported evidence kind",
            )
            _validate_relative_path(item["path"], label=f"{case_id} evidence path")
            _require(
                isinstance(item["supports"], list) and item["supports"],
                f"{case_id} evidence has no claims",
            )
            _validate_evidence_url(
                item["url"],
                repository_url=case["repository_url"],
                commit=case["commit"],
                evidence_path=item["path"],
                evidence_kind=item["kind"],
            )
            covered_claims.update(item["supports"])
            evidence_urls.add(item["url"])
        _require(
            {"build_path", "artifact_identity"} <= covered_claims,
            f"{case_id} evidence does not cover build path and artifact identity",
        )
        strata[f"{case['build_system']}-{base['size_stratum']}"] += 1

    _require(
        metadata["case_protocol_sha256"] == canonical_sha256(cases),
        "Case protocol digest drifted",
    )
    return {
        "valid": True,
        "protocolization_id": metadata["id"],
        "canonical_sha256": canonical_sha256(protocol),
        "case_protocol_sha256": canonical_sha256(cases),
        "base_preregistration_sha256": preregistration_digest,
        "cases": len(cases),
        "artifact_oracles": len(artifact_names),
        "unique_evidence_urls": len(evidence_urls),
        "strata": dict(sorted(strata.items())),
        "collection_authorized": metadata["collection_authorized"],
    }


def render_markdown(protocol: dict[str, Any], summary: dict[str, Any]) -> str:
    lines = [
        "# Forge C/C++ 正式实验逐项目构建协议",
        "",
        "> 该文档由 `scripts/forge_formal_case_protocol.py render` 确定性生成。",
        "> 它只记录结果盲态静态审计，不授权模型调用或正式采集。",
        "",
        "## 协议摘要",
        "",
        f"- 协议：`{summary['protocolization_id']}`",
        f"- 项目数：{summary['cases']}",
        f"- Artifact oracle 数：{summary['artifact_oracles']}",
        f"- 固定证据 URL 数：{summary['unique_evidence_urls']}",
        f"- 基础预注册 SHA-256：`{summary['base_preregistration_sha256']}`",
        f"- Case protocol SHA-256：`{summary['case_protocol_sha256']}`",
        "- 正式采集授权：否",
        "",
        "## 逐项目协议",
        "",
        "| Case | 构建系统 | 源码目录 | 构建目标 | 必需产物 | 固定证据 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for case in protocol["cases"]:
        targets = ", ".join(f"`{target}`" for target in case["recipe"]["build_targets"])
        artifacts = ", ".join(
            f"`{artifact['staged_relative_path']}` ({artifact['artifact_type']})"
            for artifact in case["artifact_oracle"]["required_artifacts"]
        )
        evidence = "<br>".join(
            f"[{item['path']}]({item['url']})" for item in case["evidence"]
        )
        lines.append(
            f"| `{case['id']}` | {case['build_system']} | "
            f"`{case['recipe']['source_subdir']}` | {targets} | {artifacts} | {evidence} |"
        )
    lines.extend(
        [
            "",
            "## 冻结边界",
            "",
            "- v1-v8 manifest、Schema、validator 与既有 physical-attempt ledger 不因本协议改变。",
            "- 所有项目选择、构建目标和 artifact oracle 均在正式模型请求前确定。",
            "- 禁止宽泛 artifact glob、运行后 replacement/backfill、provider fallback 和静默重试。",
            "- 本协议通过后仍需冻结 formal manifest、Schema、runner/image/prompt/budget hash，",
            "  完成双 provider Compose/DooD preflight，并由用户另行授权采集预算。",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("validate", "render"), nargs="?", default="validate"
    )
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--preregistration", type=Path, default=DEFAULT_PREREGISTRATION)
    parser.add_argument("--output", type=Path, default=DEFAULT_MARKDOWN)
    args = parser.parse_args(argv)
    try:
        protocol = load_protocol(args.protocol)
        preregistration = load_preregistration(args.preregistration)
        summary = validate_protocol(protocol, preregistration)
    except CaseProtocolError as exc:
        print(json.dumps({"valid": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    if args.command == "render":
        markdown = render_markdown(protocol, summary)
        args.output.write_text(markdown, encoding="utf-8", newline="\n")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
