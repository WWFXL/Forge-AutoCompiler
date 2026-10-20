"""共享精确暂存：接受仓库内构建产生的版本化共享库链接，拒绝越界和歧义。"""

import shlex


def delivery_command(artifacts: tuple[str, ...]) -> str:
    """链接只用于定位；交付仍为真实普通文件，保持原模式并参加严格重放。"""
    script = """import json, shutil
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
    if len(matches) != 1:
        raise RuntimeError('交付源必须唯一: ' + target + ' candidates=' + str(matches))
    selected.append((matches[0], Path('/artifacts') / target))
for source, destination in selected:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    shutil.copymode(source, destination)
print('FORGE_UNIFIED_STAGED', json.dumps(artifacts))
"""
    return "python3 -c " + shlex.quote(script.replace("ARTIFACTS", repr(artifacts)))
