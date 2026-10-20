"""固定比较队列的只读独立分层复核；只使用标准库。"""

import hashlib
import json
import os
import stat
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path


def load(p):
    return json.loads(p.read_text())


def sha(p):
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1048576), b""):
            h.update(b)
    return h.hexdigest()


def canonical(x):
    return hashlib.sha256(
        json.dumps(
            x, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def verify_seal(root):
    rows = []
    for d, ds, fs in os.walk(root, followlinks=False):
        for n in sorted(ds + fs):
            p = Path(d) / n
            rel = p.relative_to(root).as_posix()
            m = p.lstat().st_mode
            if rel in ("inventory.json", "seal.json"):
                continue
            if stat.S_ISLNK(m):
                target = os.readlink(p)
                b = os.fsencode(target)
                rows.append(
                    dict(
                        path=rel,
                        type="symlink",
                        target=target,
                        size=len(b),
                        sha256=hashlib.sha256(b).hexdigest(),
                    )
                )
            elif stat.S_ISREG(m):
                rows.append(
                    dict(path=rel, type="file", size=p.stat().st_size, sha256=sha(p))
                )
            else:
                assert stat.S_ISDIR(m)
    rows.sort(key=lambda x: x["path"])
    assert rows == load(root / "inventory.json")
    seal = load(root / "seal.json")
    assert canonical(rows) == seal["inventory_canonical_sha256"]
    return seal


def command_state(c):
    return (
        "not_observed"
        if c is None
        else ("passed" if c["exit_code"] == 0 and not c["timed_out"] else "failed")
    )


def audit_cohort(c):
    root = Path(c["root"])
    seal = verify_seal(root)
    p = load(root / "protocol.json")
    r = load(root / "result.json")
    assert p["identity"] == r["identity"] == seal["identity"] == c["identity"]
    if c["inventory_sha256"] is not None:
        assert seal["inventory_canonical_sha256"] == c["inventory_sha256"]
    assert len(r["arms"]) + len(r["not_observed"]) == len(p["schedule"]) == c["slots"]
    projects = {x["name"]: x for x in p["projects"]}
    rows = []
    for slot, row in zip(p["schedule"], r["arms"]):
        assert all(row[k] == v for k, v in slot.items())
        arm = "tool" if slot["method"] == "strong_tool_agent" else "plan"
        folder = root / (row["name"] + "-" + arm)
        (sp,) = folder.glob(".compile-sessions/*/*/session.json")
        s = load(sp)
        src = Path(s["leadagent_repo_dir"])
        hashes = load(folder / "original-source-hashes.json")
        task = projects[slot["project"]]["task"]
        assert all((src / n).is_file() and sha(src / n) == h for n, h in hashes.items())
        commands = s["commands"]
        build = [x for x in commands if x["role"] == "build"]
        stage = [x for x in commands if x["role"] == "artifact_stage"]
        fixed = []
        for step in task["verification_steps"]:
            matches = [
                x
                for x in commands
                if x["role"] == "smoke"
                and x["command"] == step["command"]
                and x["workdir"] == step.get("workdir", "/workspace/repo")
            ]
            fixed.append(command_state(matches[-1] if matches else None))
        author = {"status": "not_observed", "actual_passed": None, "notrun": None}
        xml = src.parent / "forge-ctest.xml"
        logs = "\n".join(
            Path(x["log_path"]).read_text(errors="replace")
            for x in commands
            if x["role"] == "smoke"
        )
        if xml.exists():
            tree = ET.parse(xml)
            tests = list(tree.iter("testcase"))
            statuses = Counter(
                "failed"
                if any(t.find(k) is not None for k in ("failure", "error"))
                else "notrun"
                if t.get("status", "run") != "run" or t.find("skipped") is not None
                else "passed"
                for t in tests
            )
            count = {"yaml-cpp": 3, "simdutf": 94, "snappy": 1}[slot["project"]]
            author = dict(
                status="passed"
                if len(tests) == count and statuses == {"passed": count}
                else "failed",
                expected_count=count,
                status_counts=dict(statuses),
                actual_passed=statuses["passed"],
                notrun=statuses["notrun"],
            )
        elif "Test project /workspace/repo/build" in logs:
            author["status"] = "observed_not_established"
        replay = s["replay_attempts"][-1] if s["replay_attempts"] else None
        replay_state = (
            "not_observed"
            if replay is None
            else (
                "passed"
                if replay["status"] == "passed"
                and all(x["passed"] for x in replay["checks"])
                else "failed"
            )
        )
        delivery = "not_observed"
        if stage:
            delivery = command_state(stage[-1])
            if delivery == "passed":
                assert sorted(
                    x.relative_to(Path(s["leadagent_artifacts_dir"])).as_posix()
                    for x in Path(s["leadagent_artifacts_dir"]).rglob("*")
                    if x.is_file()
                ) == sorted(task["artifact_paths"])
        if replay_state == "passed":
            rp = sp.parent / "replay" / replay["attempt_id"]
            rs = rp / "workspace/repo"
            assert all(
                (rs / n).is_file() and sha(rs / n) == h for n, h in hashes.items()
            )
            for a in replay["artifacts"]:
                assert a["passed"] and a["expected_sha256"] == a[
                    "actual_sha256"
                ] == sha(rp / "artifacts" / a["path"]) == sha(
                    Path(s["leadagent_artifacts_dir"]) / a["path"]
                )
        refs = {s["container_name"], s["container_id"]}
        for a in s["replay_attempts"]:
            refs.update(a[k] for k in ("container_id", "container_name") if a.get(k))
        for ref in refs:
            check = subprocess.run(
                ["docker", "inspect", "--type", "container", ref],
                capture_output=True,
                text=True,
                timeout=15,
            )
            assert check.returncode == 1 and (
                "No such object" in check.stderr or "No such container" in check.stderr
            )
        strict = row["strict_completed"]
        build_state = command_state(build[-1] if build else None)
        if strict:
            assert (
                build_state == author["status"] == delivery == replay_state == "passed"
                and all(x == "passed" for x in fixed)
                and s["status"] == "completed"
            )
        rows.append(
            dict(
                **slot,
                build=build_state,
                fixed_task_oracle=fixed,
                author_tests=author,
                stage=delivery,
                clean_replay=replay_state,
                original_source="passed",
                cleanup="passed",
                strict_completed=strict,
                build_pass_without_strict=build_state == "passed" and not strict,
            )
        )
    return dict(
        identity=c["identity"],
        inventory_sha256=seal["inventory_canonical_sha256"],
        denominator=c["slots"],
        observed=len(rows),
        not_observed=len(r["not_observed"]),
        strict=sum(x["strict_completed"] for x in rows),
        build_pass_without_strict=sum(x["build_pass_without_strict"] for x in rows),
        layer_counts={
            key: dict(
                Counter(
                    x[key] if key != "author_tests" else x[key]["status"] for x in rows
                )
            )
            for key in (
                "build",
                "author_tests",
                "stage",
                "clean_replay",
                "original_source",
                "cleanup",
            )
        },
        rows=rows,
    )


if __name__ == "__main__":
    rules = Path(sys.argv[1])
    out = Path(sys.argv[2])
    p = load(rules)
    result = dict(
        valid=True,
        identity=p["identity"],
        rules_sha256=sha(rules),
        implementation_sha256=sha(Path(__file__)),
        cohorts=[audit_cohort(c) for c in p["fixed_cohorts"]],
    )
    with out.open("x") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in result.items() if k != "cohorts"}))
    print(
        json.dumps(
            [{k: v for k, v in c.items() if k != "rows"} for c in result["cohorts"]],
            ensure_ascii=False,
        )
    )
