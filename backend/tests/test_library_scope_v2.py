"""完整示例义务不能被关示例或只生成部分程序绕过。"""

import importlib
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
comparison = importlib.import_module("forge_build_library_comparison_v2")


@pytest.mark.parametrize("enabled,count", [(False, 10), (True, 9)])
def test_scope_rejects_disabled_or_missing_author_example(tmp_path, enabled, count):
    (tmp_path / "build").mkdir()
    (tmp_path / "build/CMakeCache.txt").write_text("ELFIO_BUILD_EXAMPLES:BOOL=" + ("ON" if enabled else "OFF") + "\n")
    for name in comparison.EXAMPLES[:count]:
        path = tmp_path / "build/examples" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile("/bin/true", path)
    result = subprocess.run(shlex.split(comparison.scope_command()), cwd=tmp_path, capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert "FORGE_ELFIO_ORIGINAL_EXAMPLES 10" not in result.stdout
