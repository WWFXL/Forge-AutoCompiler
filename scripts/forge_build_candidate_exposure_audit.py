"""只读登记固定候选的有限Git命中与已审计模型轨迹，不推断全历史未见。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from forge_typed_evidence import canonical, seal, write_json


def repository_key(value):
    value = re.sub(r"^https?://github\.com/", "", value, flags=re.I).rstrip("/")
    value = re.sub(r"\.git$", "", value, flags=re.I)
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value):
        raise ValueError("必须是精确GitHub owner/name")
    return value.lower()


def exact_match(repository, text):
    name = re.escape(repository_key(repository))
    return re.search(r"(?<![a-z0-9_.-])" + name + r"(?:\.git)?(?![a-z0-9_.-])", text, re.I) is not None


def observed_model_arms(protocol, result):
    if protocol["identity"] != result["identity"]:
        raise ValueError("模型队列身份不一致")
    projects = {p["name"]: repository_key(p["task"]["repository_url"]) for p in protocol["projects"]}
    observed = []
    for row in result["arms"]:
        name = row.get("project", re.sub(r"-r\d+$", "", row["name"]))
        if name not in projects:
            raise ValueError("模型观察未绑定固定项目")
        usage = row["agent_usage"]
        if usage["model_requests"] > 0:
            observed.append({"repository": projects[name], "name": row["name"], "arm": row["arm"], "model_requests": usage["model_requests"], "strict_completed": row["strict_completed"]})
    return observed


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True).stdout


def collect(repo, protocol, root):
    if datetime.now(timezone.utc) >= datetime.fromisoformat(protocol["deadline_utc"]):
        raise ValueError("采集截止时间已到")
    candidates = [repository_key(c["repository"]) for c in protocol["candidates"]]
    if len(candidates) != 18 or len(set(candidates)) != 18:
        raise ValueError("候选必须为固定18个不同槽位")
    root.mkdir(parents=True, exist_ok=False)
    write_json(root / "protocol.json", protocol)
    receipts = []

    def consume(path):
        raw = path.read_bytes()
        index = len(receipts)
        target = root / "consumed" / f"{index:04d}.json"
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(raw)
        receipts.append({"path": str(path), "snapshot": str(target.relative_to(root)), "sha256": hashlib.sha256(raw).hexdigest()})
        return json.loads(raw)

    hits = []
    file_hashes = {}
    for revision in protocol["history_revisions"]:
        if git(repo, "rev-parse", revision + "^{commit}").decode().strip() != revision:
            raise ValueError("检索revision必须为完整commit")
        args = ["grep", "--no-color", "-I", "-n", "-i", "-F"]
        for candidate in candidates:
            args.extend(["-e", candidate])
        proc = subprocess.run(["git", "-C", str(repo), *args, revision, "--", *protocol["search_paths"]], capture_output=True)
        if proc.returncode not in (0, 1):
            raise ValueError("Git检索失败")
        for line in proc.stdout.decode("utf-8").splitlines():
            rev, name, number, text = line.split(":", 3)
            for candidate in candidates:
                if not exact_match(candidate, text):
                    continue
                key = rev + ":" + name
                if key not in file_hashes:
                    raw = git(repo, "show", key)
                    target = root / "git-files" / rev / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(raw)
                    file_hashes[key] = hashlib.sha256(raw).hexdigest()
                hits.append({"repository": candidate, "revision": rev, "path": name, "line": int(number), "text": text, "file_sha256": file_hashes[key]})
    cohorts = []
    for item in protocol["model_cohorts"]:
        parent = Path(item["root"])
        parent_seal = consume(parent / "seal.json")
        parent_inventory = consume(parent / "inventory.json")
        if canonical(parent_inventory) != item["inventory_sha256"] or parent_seal["inventory_canonical_sha256"] != item["inventory_sha256"]:
            raise ValueError("父队列inventory不一致")
        audit = consume(Path(item["audit"]))
        if not audit["valid"] or audit["issues"]:
            raise ValueError("父独立审计未通过")
        lookup = {r["path"]: r for r in parent_inventory}
        for name in ("protocol.json", "result.json"):
            if hashlib.sha256((parent / name).read_bytes()).hexdigest() != lookup[name]["sha256"]:
                raise ValueError("父队列消费文件被改变")
        frozen_protocol = consume(parent / "protocol.json")
        result = consume(parent / "result.json")
        cohorts.append({"identity": frozen_protocol["identity"], "arms": observed_model_arms(frozen_protocol, result)})
    rows = []
    for item, key in zip(protocol["candidates"], candidates, strict=True):
        model = [{"identity": c["identity"], **a} for c in cohorts for a in c["arms"] if a["repository"] == key]
        rows.append({**item, "repository_key": key, "git_hits": sum(h["repository"] == key for h in hits), "observed_model_arms_in_scope": model, "maintainer_association": key.split("/")[0], "holdout_assigned": False})
    write_json(root / "git-hits.json", hits)
    write_json(root / "consumed-receipts.json", receipts)
    write_json(
        root / "result.json", {"identity": protocol["identity"], "candidates": rows, "cohorts": cohorts, "provider_calls": 0, "new_build_runs": 0, "scope": "固定revision/路径/队列；无命中不证明全历史或训练未见，相同owner不是代码亲缘证明"}
    )
    return seal(root, protocol, repo)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(collect(Path.cwd(), json.loads(args.protocol.read_text()), args.output), ensure_ascii=False))


if __name__ == "__main__":
    main()
