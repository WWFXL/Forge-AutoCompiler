#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# docker.sh 已被历史实验 manifest 冻结。这里复用其命令实现，
# 只把宿主机身份门禁替换为通用 Docker 能力检查。
# shellcheck source=require-docker-runtime.sh
source "$SCRIPT_DIR/require-docker-runtime.sh"
# shellcheck source=docker.sh
source "$SCRIPT_DIR/docker.sh"

if [ -z "${FORGE_HOST_UID:-}" ] && [ -z "${FORGE_HOST_GID:-}" ]; then
    export FORGE_HOST_UID="$(id -u)"
    export FORGE_HOST_GID="$(id -g)"
elif [ -z "${FORGE_HOST_UID:-}" ] || [ -z "${FORGE_HOST_GID:-}" ]; then
    echo "ERROR: FORGE_HOST_UID and FORGE_HOST_GID must be configured together." >&2
    exit 1
fi

require_ubuntu_native_docker() {
    require_docker_runtime "$@"
}

main "$@"
