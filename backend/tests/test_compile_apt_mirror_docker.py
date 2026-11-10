"""显式运行的 APT 集成检查；只安装依赖，不调用模型或运行正式实验。"""

import json
import os
import time

import pytest

from deerflow.compile.docker_runtime import CompileDockerRuntime, RuntimeConfig
from deerflow.compile.manager import CompileSessionManager
from deerflow.compile.paths import get_replay_recipe_dir
from deerflow.config.paths import Paths

pytestmark = pytest.mark.skipif(os.getenv("FORGE_RUN_DOCKER_INTEGRATION") != "1", reason="需显式启用 Docker 网络集成检查")


def test_compile_and_clean_replay_install_dependencies_from_https_mirror(tmp_path):
    image = "autocompiler:gcc13-https-v1"
    paths = Paths(base_dir=tmp_path / "data", workspace_root=tmp_path, host_workspace_root=str(tmp_path))
    manager = CompileSessionManager(paths=paths, default_image=image, parallel_jobs=2)
    runtime = CompileDockerRuntime(manager=manager, config=RuntimeConfig(image=image, parallel_jobs=2))
    session = manager.create_session("apt-mirror", "https://github.com/ggerganov/ggmorse")
    replay = None
    rows = []
    try:
        runtime.create_container(session)
        recipe = get_replay_recipe_dir(session.session_id, session.thread_id, "apt-check", paths)
        recipe.mkdir(parents=True, exist_ok=True)
        (recipe / "build.sh").write_text("#!/bin/bash\nset -euo pipefail\n")
        replay = runtime.create_replay_container(session, attempt_id="apt-check")
        assert replay.image_id == session.image_id
        # 两个独立容器均从原始镜像开始；与 ggmorse 原失败使用相同依赖集合。
        for role, container_id in (("compile", session.container_id), ("replay", replay.container_id)):
            for phase, command in (
                ("sources", "cat /etc/apt/sources.list.d/ubuntu.sources"),
                ("update", "apt-get -o Acquire::Retries=0 update --error-on=any"),
                ("install", "DEBIAN_FRONTEND=noninteractive apt-get -o Acquire::Retries=0 install -y --no-install-recommends build-essential cmake git libsdl2-dev xorg-dev libglu1-mesa-dev"),
                ("usable", "pkg-config --exists sdl2 gl && gcc --version && cmake --version"),
            ):
                started = time.monotonic()
                log = tmp_path / f"{role}-{phase}.log"
                result = runtime.exec_container(session, container_id=container_id, command=command, workdir="/workspace", timeout_seconds=180, strict_shell=True, log_path=str(log))
                rows.append(dict(role=role, phase=phase, exit_code=result.exit_code, seconds=time.monotonic() - started, log=str(log)))
                assert result.exit_code == 0, f"{role}/{phase} 未通过，见 {log}"
                if phase == "sources":
                    assert "URIs: https://mirrors.ustc.edu.cn/ubuntu/" in result.combined_output
                    assert "noble-security" in result.combined_output
                    assert "Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg" in result.combined_output
    finally:
        replay_cleanup = runtime.stop_and_remove_replay_container(session, replay) if replay else None
        compile_cleanup = runtime.stop_and_remove_container(session)
        summary = dict(image_id=session.image_id, rows=rows, compile_cleanup=compile_cleanup.succeeded, replay_cleanup=replay_cleanup.succeeded if replay_cleanup else None)
        (tmp_path / "mirror-check.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(summary, ensure_ascii=False))
        assert compile_cleanup.succeeded
        if replay_cleanup:
            assert replay_cleanup.succeeded
