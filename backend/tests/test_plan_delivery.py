"""真实ELF暂存及链接边界回归；保持精确普通文件交付。"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from deerflow.compile.plan_delivery import delivery_command


def run(source, delivery):
    command = delivery_command(("library.so",)).replace("/artifacts", str(delivery))
    return subprocess.run(["bash", "-c", command], cwd=source, capture_output=True, text=True)


def test_internal_versioned_elf_link_stages_plain_file_with_mode(tmp_path):
    source, output = tmp_path / "source", tmp_path / "output"
    source.mkdir()
    original = source / "library.so.3.1"
    original.write_bytes(Path(sys.executable).read_bytes())
    original.chmod(0o755)
    (source / "library.so.3").symlink_to(original.name)
    (source / "library.so").symlink_to("library.so.3")
    result = run(source, output)
    assert result.returncode == 0, result.stderr
    copied = output / "library.so"
    assert not copied.is_symlink() and copied.read_bytes() == original.read_bytes() and os.access(copied, os.X_OK)


@pytest.mark.parametrize("kind", ["outside", "dangling", "cycle", "ambiguous", "missing"])
def test_unsafe_or_ambiguous_link_never_delivers(tmp_path, kind):
    source, output = tmp_path / "source", tmp_path / "output"
    source.mkdir()
    if kind == "outside":
        (source / "library.so").symlink_to(Path(sys.executable).resolve())
    elif kind == "dangling":
        (source / "library.so").symlink_to("absent")
    elif kind == "cycle":
        (source / "library.so").symlink_to("library.so")
    elif kind == "ambiguous":
        for name in ("first", "second"):
            folder = source / name
            folder.mkdir()
            (folder / "library.so").write_bytes(Path(sys.executable).read_bytes())
    result = run(source, output)
    assert result.returncode != 0 and not output.exists()
