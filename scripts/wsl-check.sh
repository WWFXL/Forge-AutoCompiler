#!/usr/bin/env bash
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
missing=()

# shellcheck source=require-ubuntu-native-docker.sh
source "$SCRIPT_DIR/require-ubuntu-native-docker.sh"

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
        echo "Install Docker Engine and the Compose v2 plugin inside WSL2 Ubuntu."
    fi
    exit 1
fi

require_ubuntu_native_docker
echo "OK: docker compose"

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
echo "WSL2 Ubuntu + native Docker prerequisites are ready."
echo "Next: make config (first run), make compile-image, then make docker-start"
