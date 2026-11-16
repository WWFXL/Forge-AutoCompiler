"""从独立工程运行读取结果，不修改E58原件或效果分母。"""

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = Path("/home/yiwei/.codex/outputs")
V1 = RAW / "forge-e58-failure-repair-2026-11-17-v1"
V3 = RAW / "forge-e58-failure-repair-2026-11-17-v3"


def read(path):
    return json.loads(path.read_text())


def main():
    rows = []
    for name in ("smenu", "quickjs", "zstd", "libtasn1"):
        root = (V3 if name == "libtasn1" else V1) / name
        result_path = root / "result.json"
        result = read(result_path)
        assert result["layers"]["reproducible_delivery_completed"], name
        assert result["cleanup"]["succeeded"], name
        session_path = next(root.glob(".compile-sessions/*/*/session.json"))
        session = read(session_path)
        rows.append(
            dict(
                project=name,
                raw=str(root),
                result_sha256=hashlib.sha256(result_path.read_bytes()).hexdigest(),
                layers=result["layers"],
                cleanup=result["cleanup"],
                source_unchanged=result["source_unchanged"],
                original_changes=[c for c in result.get("source_protection", {}).get("changes", []) if c["kind"] != "added"],
                wall_seconds=result["arm_total_wall_seconds"],
                failed_commands=[dict(command_id=c["command_id"], command=c["command"], exit_code=c["exit_code"], log_path=c["log_path"]) for c in session["commands"] if c.get("exit_code") not in (None, 0)],
                reset_command_bytes=[len(c["command"].encode()) for c in session["commands"] if "FORGE_GENERATED_RESET" in c["command"]],
                replay_status=[a["status"] for a in session["replay_attempts"]],
            )
        )
    cases = read(V1 / "cases.json")
    refs = {c["project"]: c["reference"] for c in cases}
    for name, payload in [
        ("summary.json", dict(kind="zero_provider_engineering", provider_calls=0, scientific_effect_observations=0, rows=rows)),
        ("corrected-references.json", dict(source_fixture="benchmarks/fixtures/harness-update-comparison-v1/tasks.json", references=refs)),
    ]:
        (HERE / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
