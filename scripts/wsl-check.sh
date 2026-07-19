#!/usr/bin/env bash
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
missing=()

echo "=========================================="
echo "  Forge-AutoCompiler WSL2 Preflight"
echo "=========================================="
echo ""

if ! grep -qi microsoft /proc/sys/kernel/osrelease 2>/dev/null; then
    echo "ERROR: This command must run inside WSL2."
    echo "From PowerShell, enter WSL with: wsl -d Ubuntu"
    exit 1
fi

echo "Distribution: ${WSL_DISTRO_NAME:-unknown}"
echo "Repository:   $PROJECT_ROOT"
echo ""

for command in git make python3 docker; do
    if command -v "$command" >/dev/null 2>&1; then
        echo "OK: $command ($(command -v "$command"))"
    else
        echo "MISSING: $command"
        missing+=("$command")
    fi
done

if [ ${#missing[@]} -gt 0 ]; then
    echo ""
    if [[ " ${missing[*]} " == *" make "* ]] || [[ " ${missing[*]} " == *" python3 "* ]] || [[ " ${missing[*]} " == *" git "* ]]; then
        echo "Install the missing Linux prerequisites explicitly:"
        echo "  sudo apt update && sudo apt install -y build-essential git python3"
    fi
    if [[ " ${missing[*]} " == *" docker "* ]]; then
        echo "Enable Docker Desktop > Settings > Resources > WSL Integration for ${WSL_DISTRO_NAME:-this distribution},"
        echo "or intentionally install Docker Engine inside this WSL distribution."
    fi
    exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
    echo "ERROR: Docker Compose v2 is unavailable in WSL."
    echo "Enable Docker Desktop WSL integration or install the Compose v2 plugin for the WSL Docker Engine."
    exit 1
fi
echo "OK: docker compose"

if ! docker info >/dev/null 2>&1; then
    echo "ERROR: The Linux Docker daemon is not reachable from this WSL distribution."
    echo "Start Docker Desktop, or start the native WSL Docker service, and rerun this check."
    exit 1
fi
docker_os="$(docker info --format '{{.OperatingSystem}}' 2>/dev/null || echo unknown)"
docker_context="$(docker context show 2>/dev/null || echo unknown)"
echo "OK: Docker daemon ($docker_os; context=$docker_context)"
echo "NOTE: Run all Forge Docker commands against this same daemon; Docker Desktop and native WSL images are not shared."

if docker image inspect autocompiler:gcc13 >/dev/null 2>&1; then
    echo "OK: compile image (autocompiler:gcc13)"
else
    echo "MISSING: compile image autocompiler:gcc13"
    echo "Build it before the first compile task: make compile-image"
fi

if [[ "$PROJECT_ROOT" == /mnt/* ]]; then
    echo ""
    echo "NOTE: The repository is on a Windows-mounted drive ($PROJECT_ROOT)."
    echo "This is supported, but cloning under ~/src usually gives faster file watching and dependency installs."
fi

echo ""
echo "WSL2 + Docker prerequisites are ready."
echo "Next: make config (first run), make compile-image, then make docker-start"
