#!/usr/bin/env python3
"""Issue #155 checkpoint primary canary amendment 授权协议与执行适配器。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = Path(os.environ.get("FORGE_REPO_ROOT", SCRIPT_ROOT.parent)).resolve()
DEFAULT_MANIFEST = (
    REPO_ROOT
    / "benchmarks"
    / "manifests"
    / "cpp-verifier-checkpoint-primary-canary-amendment-authorized.json"
)
DEFAULT_OUTPUT_DIR = Path(
    "/workspace/.compile-sessions/benchmark-evidence-checkpoint-primary-canary-amendment"
)
SUPERSEDED_OUTPUT_DIR = Path(
    "/workspace/.compile-sessions/benchmark-evidence-checkpoint-primary-canary"
)

SCHEMA_VERSION = "forge-checkpoint-primary-canary-amendment-authorized-1.0.0"
DOCUMENT_TYPE = "forge_checkpoint_primary_canary_amendment_authorized"
AUTHORIZATION_BASELINE = "9feb832da1f4b124694260de1b487ea645ae55af"
CANDIDATE_PATH = "benchmarks/manifests/cpp-verifier-checkpoint-primary-canary-amendment-candidate.json"
CANDIDATE_CANONICAL_SHA256 = (
    "d0598b549301a2efbe431e2bfa7f6f21c4ba32e2c3eae1b078935630f1ffb704"
)
REACHABILITY_MARKER = "amendment-reachability-attempt.json"
PAIR_MARKER = "amendment-controlled-pair-attempt.json"
PROTOCOL_ARTIFACT_PATHS = (
    "scripts/forge_checkpoint_primary_canary_amendment.py",
    "scripts/forge_checkpoint_primary_canary_amendment_authorized.py",
    "backend/tests/test_forge_checkpoint_primary_canary_amendment_authorized.py",
    "benchmarks/preregistrations/cpp-verifier-checkpoint-primary-canary-amendment-authorized.md",
)


class AuthorizedAmendmentError(RuntimeError):
    """授权 identity、冻结组件或历史 evidence 发生漂移。"""


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AuthorizedAmendmentError(f"无法加载协议模块: {path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


candidate_protocol = _load_module(
    "forge_checkpoint_primary_canary_amendment_authorized_candidate",
    SCRIPT_ROOT / "forge_checkpoint_primary_canary_amendment.py",
)
primary_canary = _load_module(
    "forge_checkpoint_primary_canary_amendment_authorized_parent",
    SCRIPT_ROOT / "forge_checkpoint_primary_canary.py",
)
build_layout = _load_module(
    "forge_checkpoint_primary_canary_amendment_authorized_layout",
    SCRIPT_ROOT / "forge_checkpoint_windows_build_layout.py",
)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AuthorizedAmendmentError(f"无法读取 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise AuthorizedAmendmentError(f"JSON 根节点必须是对象: {path}")
    return value


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _candidate_manifest(repo_root: Path) -> dict[str, Any]:
    path = repo_root / CANDIDATE_PATH
    candidate = candidate_protocol.validate_manifest(_load_json(path), repo_root)
    if candidate_protocol.canonical_sha256(candidate) != CANDIDATE_CANONICAL_SHA256:
        raise AuthorizedAmendmentError(
            "amendment candidate canonical identity 发生漂移"
        )
    return candidate


def _protocol_artifacts(repo_root: Path) -> list[dict[str, str]]:
    artifacts: list[dict[str, str]] = []
    for relative_path in PROTOCOL_ARTIFACT_PATHS:
        path = repo_root / relative_path
        if not path.is_file():
            raise AuthorizedAmendmentError(f"授权协议文件缺失: {relative_path}")
        artifacts.append({"path": relative_path, "sha256": file_sha256(path)})
    return artifacts


def generate_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    candidate = _candidate_manifest(repo_root)
    amendment = candidate["amendment"]
    return {
        "schema_version": SCHEMA_VERSION,
        "document_type": DOCUMENT_TYPE,
        "scope": {
            "provider_canary_authorized": True,
            "mechanism_canary_authorized": True,
            "pilot_collection_authorized": False,
            "natural_collection_authorized": False,
            "secondary_provider_authorized": False,
        },
        "provider": amendment["provider"],
        "fault": amendment["fault"],
        "continuation": amendment["continuation"],
        "budget": amendment["budget"],
        "stopping": amendment["stopping"],
        "execution": {
            **amendment["execution"],
            "authorization_baseline_commit": AUTHORIZATION_BASELINE,
            "release_revision_policy": "descendant-compatible",
        },
        "authorization": {
            "issue_url": "https://github.com/WWFXL/Forge-AutoCompiler/issues/155",
            "authorized_reachability_attempts": 1,
            "authorized_controlled_pairs": 1,
            "stage_maximum_tokens": 245000,
            "pilot_collection_authorized": False,
        },
        "parent_candidate": {
            "path": CANDIDATE_PATH,
            "sha256": file_sha256(repo_root / CANDIDATE_PATH),
            "canonical_sha256": CANDIDATE_CANONICAL_SHA256,
        },
        "protocol_artifacts": _protocol_artifacts(repo_root),
    }


def validate_manifest(value: Any, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AuthorizedAmendmentError("authorized amendment manifest 必须是对象")
    if value != generate_manifest(repo_root):
        raise AuthorizedAmendmentError(
            "authorized amendment manifest 与冻结授权协议不一致"
        )
    return value


def verify_frozen_artifacts(
    manifest: dict[str, Any], repo_root: Path = REPO_ROOT
) -> None:
    validate_manifest(manifest, repo_root)
    candidate = _candidate_manifest(repo_root)
    candidate_protocol.verify_frozen_components(candidate, repo_root)
    parent = manifest["parent_candidate"]
    if file_sha256(repo_root / parent["path"]) != parent["sha256"]:
        raise AuthorizedAmendmentError("amendment candidate 文件 identity 发生漂移")
    for artifact in manifest["protocol_artifacts"]:
        if file_sha256(repo_root / artifact["path"]) != artifact["sha256"]:
            raise AuthorizedAmendmentError(f"授权协议制品发生漂移: {artifact['path']}")


def verify_superseded_evidence(
    manifest: dict[str, Any], output_dir: Path = SUPERSEDED_OUTPUT_DIR
) -> dict[str, Any]:
    verify_frozen_artifacts(manifest)
    candidate = _candidate_manifest(REPO_ROOT)
    return candidate_protocol.verify_superseded_evidence(candidate, output_dir)


_parent_release_identity = primary_canary.require_release_identity


def require_release_identity(
    manifest: dict[str, Any], repo_root: Path = REPO_ROOT
) -> dict[str, str]:
    result = _parent_release_identity(manifest, repo_root)
    merge_base = primary_canary._git(
        repo_root,
        "merge-base",
        manifest["execution"]["authorization_baseline_commit"],
        result["revision"],
    )
    if merge_base != manifest["execution"]["authorization_baseline_commit"]:
        raise AuthorizedAmendmentError("当前 release 不是授权 baseline 的后代")
    return result


primary_canary.DEFAULT_MANIFEST = DEFAULT_MANIFEST
primary_canary.DEFAULT_OUTPUT_DIR = DEFAULT_OUTPUT_DIR
primary_canary.REACHABILITY_MARKER = REACHABILITY_MARKER
primary_canary.PAIR_MARKER = PAIR_MARKER
primary_canary.validate_manifest = validate_manifest
primary_canary.verify_frozen_artifacts = verify_frozen_artifacts
primary_canary.require_release_identity = require_release_identity


def run_reachability(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = REPO_ROOT,
    model_factory: Callable[[dict[str, Any]], Any] | None = None,
) -> dict[str, Any]:
    validate_manifest(manifest, repo_root)
    verify_superseded_evidence(manifest)
    return primary_canary.run_reachability(
        manifest,
        output_dir=output_dir,
        repo_root=repo_root,
        model_factory=model_factory,
    )


def run_controlled_pair(
    manifest: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = REPO_ROOT,
    model_factory: Callable[[dict[str, Any], str], Any] | None = None,
) -> dict[str, Any]:
    validate_manifest(manifest, repo_root)
    verify_superseded_evidence(manifest)
    with build_layout.use_windows_safe_build_layout(primary_canary):
        return primary_canary.run_controlled_pair(
            manifest,
            output_dir=output_dir,
            repo_root=repo_root,
            model_factory=model_factory,
        )


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "generate",
            "validate",
            "validate-evidence",
            "reachability",
            "controlled-pair",
        ),
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--superseded-output-dir", type=Path, default=SUPERSEDED_OUTPUT_DIR
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "generate":
            manifest = generate_manifest()
            _write_json(args.manifest, manifest)
            result = {
                "status": "generated",
                "manifest_sha256": canonical_sha256(manifest),
            }
        else:
            manifest = validate_manifest(_load_json(args.manifest))
            verify_frozen_artifacts(manifest)
            if args.command == "validate":
                result = {
                    "status": "valid",
                    "provider_calls": 0,
                    "provider_canary_authorized": True,
                    "mechanism_canary_authorized": True,
                    "pilot_collection_authorized": False,
                    "stage_maximum_tokens": manifest["budget"]["stage_maximum_tokens"],
                    "manifest_sha256": canonical_sha256(manifest),
                }
            elif args.command == "validate-evidence":
                result = {
                    "status": "valid",
                    "provider_calls": 0,
                    "superseded_evidence": verify_superseded_evidence(
                        manifest, args.superseded_output_dir
                    ),
                    "manifest_sha256": canonical_sha256(manifest),
                }
            elif args.command == "reachability":
                result = run_reachability(manifest, output_dir=args.output_dir)
            else:
                result = run_controlled_pair(manifest, output_dir=args.output_dir)
    except (
        AuthorizedAmendmentError,
        candidate_protocol.AmendmentError,
        primary_canary.CanaryError,
        build_layout.BuildLayoutError,
        OSError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
