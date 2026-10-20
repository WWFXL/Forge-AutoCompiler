"""共同暂存新身份：同内容及模式的副本只构成一个交付身份。"""

import shlex


def equivalent_delivery_command(artifacts: tuple[str, ...]) -> str:
    """链接只用于定位；交付仍为真实普通文件，保持原模式并参加严格重放。"""
    script = """import hashlib, json, shutil
from pathlib import Path
root = Path.cwd().resolve()
artifacts = ARTIFACTS
selected = []
for target in artifacts:
    matches = []
    for path in root.rglob(Path(target).name):
        if not path.is_file() and not path.is_symlink():
            continue
        try:
            resolved = path.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise RuntimeError('交付候选链接无效: ' + str(path)) from exc
        if not resolved.is_relative_to(root) or not resolved.is_file():
            raise RuntimeError('交付候选越界或不是普通文件: ' + str(path))
        with resolved.open('rb') as stream:
            magic = stream.read(8)
        if magic.startswith(b'\\x7fELF') or magic == b'!<arch>\\n':
            matches.append(resolved)
    identities = {}
    for candidate in sorted(set(matches)):
        stat = candidate.stat()
        fingerprint = hashlib.sha256()
        with candidate.open('rb') as stream:
            for block in iter(lambda: stream.read(1048576), b''):
                fingerprint.update(block)
        content_sha256 = fingerprint.hexdigest()
        identity = (stat.st_size, content_sha256, stat.st_mode & 0o777)
        identities.setdefault(identity, candidate)
    if len(identities) != 1:
        raise RuntimeError('交付源必须唯一: ' + target + ' candidates=' + str(matches))
    selected.append((next(iter(identities.values())), Path('/artifacts') / target))
for source, destination in selected:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    shutil.copymode(source, destination)
print('FORGE_UNIFIED_STAGED', json.dumps(artifacts))
"""
    return "python3 -c " + shlex.quote(script.replace("ARTIFACTS", repr(artifacts)))


def with_equivalent_delivery(plan):
    """只更换共同暂存算法；不更换作者测试或交付集合。"""
    from deerflow.compile.plan_workflow import BuildPlan

    value = plan.model_dump(mode="json")
    stages = [s for s in value["steps"] if s["role"] == "artifact_stage"]
    if len(stages) != 1:
        raise ValueError("共同方案必须只有一个暂存步骤")
    stages[0]["command"] = equivalent_delivery_command(tuple(plan.artifact_paths))
    return BuildPlan.model_validate(value)
