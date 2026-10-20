"""三个已见自然失败队列的固定14行只读分层审计。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from forge_build_validation_evidence_audit import analyze_cohort
from forge_typed_evidence import seal, write_json

EXPECTED = {
    "cpp-build-auto-provenance-probe-v1": 12,
    "cpp-build-libverto-natural-recovery-v1": 1,
    "cpp-build-libverto-natural-recovery-v2": 1,
}


def validate_protocol(protocol):
    if protocol["identity"] != "cpp-build-validation-natural-audit-v1" or protocol["provider_calls"] != 0 or protocol["docker_runs"] != 0 or not protocol["results_previously_observed"]:
        raise ValueError("回顾分析或零支出边界不符")
    cohorts = protocol["cohorts"]
    if len(cohorts) != 3 or {c["identity"]: len(c["rows"]) for c in cohorts} != EXPECTED:
        raise ValueError("必须保留三个队列全部14行，不选择成功子集")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    validate_protocol(protocol)
    root = args.output_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    write_json(root / "protocol.json", protocol)
    result = {"identity": protocol["identity"], "kind": "retrospective_stratified_analysis", "provider_calls": 0, "docker_runs": 0, "cohorts": []}
    try:
        for spec in protocol["cohorts"]:
            result["cohorts"].append(analyze_cohort(spec))
    finally:
        result["analysis_complete"] = len(result["cohorts"]) == 3
        write_json(root / "result.json", result)
        print(json.dumps(seal(root, protocol, Path(__file__).resolve().parents[1]), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
