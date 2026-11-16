"""把清理所需的原输入清单留在执行侧，不装入Agent命令和上下文。"""

import hashlib
import json
from pathlib import Path

MANIFEST_NAME = ".forge-source-inputs.json"


def manifest_bytes(names):
    return json.dumps(sorted(names), ensure_ascii=True, separators=(",", ":")).encode()


def write_manifest(root, names):
    (Path(root).parent / MANIFEST_NAME).write_bytes(manifest_bytes(names))


# 干净重建在解压/检出原源码之后、执行任何构建动作之前建立同一清单。
SNAPSHOT_SCRIPT = """import json,os,pathlib
root=pathlib.Path('/workspace/repo')
names=[]
for directory,dirs,files in os.walk(root,followlinks=False):
 dirs[:]=[d for d in dirs if d!='.git']
 for name in files+[d for d in dirs if (pathlib.Path(directory)/d).is_symlink()]:
  names.append((pathlib.Path(directory)/name).relative_to(root).as_posix())
(root.parent/'.forge-source-inputs.json').write_text(json.dumps(sorted(names),ensure_ascii=True,separators=(',',':')))
"""


def reset_script(names):
    digest = hashlib.sha256(manifest_bytes(names)).hexdigest()
    return """import hashlib,json,os,pathlib
root=pathlib.Path('/workspace/repo')
data=(root.parent/'.forge-source-inputs.json').read_bytes()
if hashlib.sha256(data).hexdigest() != 'DIGEST':
 raise RuntimeError('原输入清单缺失或发生变化，停止清理')
protected=set(json.loads(data))
for directory,dirs,files in os.walk(root,topdown=False,followlinks=False):
 p=pathlib.Path(directory)
 if '.git' in p.relative_to(root).parts: continue
 for name in files:
  f=p/name; rel=f.relative_to(root).as_posix()
  if rel not in protected: f.unlink()
 for name in dirs:
  d=p/name; rel=d.relative_to(root).as_posix()
  if name=='.git' or rel in protected: continue
  if d.is_symlink(): d.unlink()
  elif not any(d.iterdir()): d.rmdir()
print('FORGE_GENERATED_RESET')
""".replace("DIGEST", digest)
