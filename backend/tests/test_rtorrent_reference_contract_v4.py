"""实际执行生成的自包含验证脚本，复现并约束子进程缺导入问题。"""

import json
import shlex
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from forge_build_rtorrent_contract_v3 import verification_command as old_command  # noqa: E402
from forge_build_rtorrent_contract_v4 import verification_command  # noqa: E402


@pytest.mark.parametrize("fixed", [False, True])
def test_emitted_python_executes_with_empty_globals_and_all_calls(monkeypatch, capsys, fixed):
    groups = {"build-libtorrent": {"Library": ["torrent/net::Suite::a"]}, "build-rtorrent": {"Client": ["Suite::b"]}}
    logs = {}
    calls = []

    class FakePath:
        def __init__(self, value):
            self.value = value

        def __truediv__(self, value):
            return FakePath(self.value + "/" + value)

        def __str__(self):
            return self.value

        def write_text(self, text):
            logs[self.value] = text

    def run(args, **kwargs):
        calls.append((args, kwargs))
        assert "TEST_NAME" not in kwargs["env"] and kwargs["env"]["LC_ALL"] == "C"
        if args == ["/artifacts/rtorrent", "-h"]:
            assert kwargs["env"]["LD_LIBRARY_PATH"] == "/artifacts"
            return SimpleNamespace(returncode=0, stdout="Rakshasa's BitTorrent client version 0.16.25.\nUsage: rtorrent\n", stderr="")
        assert kwargs["env"]["LD_LIBRARY_PATH"] == "/workspace/prefix/lib"
        name = "torrent/net::Suite::a" if args[0].endswith("/Library") else "Suite::b"
        return SimpleNamespace(returncode=0, stdout=name + " : OK\nOK (1)\n")

    command = verification_command(groups) if fixed else old_command(groups)
    argv = shlex.split(command)
    assert argv[:2] == ["python3", "-c"]
    with monkeypatch.context() as context:
        context.setitem(sys.modules, "os", SimpleNamespace(environ={"TEST_NAME": "must-not-filter"}))
        context.setitem(sys.modules, "pathlib", SimpleNamespace(Path=FakePath))
        context.setitem(sys.modules, "subprocess", SimpleNamespace(run=run, PIPE=1, STDOUT=2))
        if fixed:
            exec(compile(argv[2], "generated-verification", "exec"), {})
        else:
            with pytest.raises(NameError, match="json"):
                exec(compile(argv[2], "generated-verification", "exec"), {})
    assert len(calls) == 3 and len(logs) == 3
    if fixed:
        summary = capsys.readouterr().out.removeprefix("FORGE_RTORRENT_FULL_TESTS=")
        assert json.loads(summary) == {"programs": [{"program": "Library", "passed": 1, "expected": 1}, {"program": "Client", "passed": 1, "expected": 1}], "cli_version": "0.16.25", "test_name_filter": False}
