from __future__ import annotations

import subprocess
from pathlib import Path
from shutil import which

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "require-ubuntu-native-docker.sh"
DOCKER_SCRIPT_PATH = REPO_ROOT / "scripts" / "docker.sh"
WSL_CHECK_PATH = REPO_ROOT / "scripts" / "wsl-check.sh"
BASH_CANDIDATES = [
    Path(r"C:\Program Files\Git\bin\bash.exe"),
    Path(which("bash")) if which("bash") else None,
]
BASH_EXECUTABLE = next(
    (str(path) for path in BASH_CANDIDATES if path is not None and path.exists() and "WindowsApps" not in str(path)),
    None,
)

if BASH_EXECUTABLE is None:
    pytestmark = pytest.mark.skip(reason="bash is required for Docker gate tests")


def _run_gate(*, overrides: str = "", env: dict[str, str] | None = None):
    helpers = """
_forge_kernel_release() { echo '6.6.0-microsoft-standard-WSL2'; }
_forge_command_exists() { return 0; }
_forge_docker_service_state() { echo active; }
_forge_docker_service_pid() { echo 42; }
_forge_process_name() { echo dockerd; }
_forge_docker_context() { echo default; }
_forge_docker_endpoint() { echo unix:///var/run/docker.sock; }
_forge_docker_operating_system() { echo 'Ubuntu 26.04 LTS'; }
_forge_docker_socket_ready() { return 0; }
_forge_docker_compose_ready() { return 0; }
"""
    command = f"source '{SCRIPT_PATH}'\n{helpers}\n{overrides}\nrequire_ubuntu_native_docker"
    return subprocess.run(
        [BASH_EXECUTABLE, "-lc", command],
        env={"PATH": "", "WSL_DISTRO_NAME": "Ubuntu", **(env or {})},
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_gate_accepts_only_the_reviewed_ubuntu_native_daemon() -> None:
    result = _run_gate()

    assert result.returncode == 0, result.stderr
    assert "provider=ubuntu-native" in result.stdout
    assert "Docker Desktop" not in result.stdout


def test_forge_docker_entrypoints_require_the_gate() -> None:
    docker_script = DOCKER_SCRIPT_PATH.read_text(encoding="utf-8")
    wsl_check = WSL_CHECK_PATH.read_text(encoding="utf-8")

    source_line = 'source "$SCRIPT_DIR/require-ubuntu-native-docker.sh"'
    assert source_line in docker_script
    assert source_line in wsl_check
    assert "require_ubuntu_native_docker --quiet" in docker_script
    assert "require_ubuntu_native_docker" in wsl_check
    assert "init|start|restart|model-preflight|logs|stop)" in docker_script


@pytest.mark.parametrize(
    ("overrides", "env", "message"),
    [
        ("", {"WSL_DISTRO_NAME": "Debian"}, "must be Ubuntu"),
        ("", {"DOCKER_CONTEXT": "desktop-linux"}, "overrides are forbidden"),
        ("_forge_docker_service_state() { echo inactive; }", None, "not active"),
        ("_forge_process_name() { echo desktop-backend; }", None, "not owned by dockerd"),
        ("_forge_docker_context() { echo desktop-linux; }", None, "context must be default"),
        ("_forge_docker_endpoint() { echo npipe:////./pipe/dockerDesktopLinuxEngine; }", None, "default Docker endpoint"),
        ("_forge_docker_socket_ready() { return 1; }", None, "not a Unix socket"),
        ("_forge_docker_operating_system() { echo 'Docker Desktop'; }", None, "not Ubuntu"),
    ],
)
def test_gate_rejects_daemon_ambiguity(
    overrides: str,
    env: dict[str, str] | None,
    message: str,
) -> None:
    result = _run_gate(overrides=overrides, env=env)

    assert result.returncode == 1
    assert message in result.stderr
    assert "Do not start or switch to Docker Desktop" in result.stderr
