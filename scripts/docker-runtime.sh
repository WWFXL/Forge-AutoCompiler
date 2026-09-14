#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# docker.sh 已被历史实验 manifest 冻结。这里复用其命令实现，
# 只把宿主机身份门禁替换为通用 Docker 能力检查。
# shellcheck source=require-docker-runtime.sh
source "$SCRIPT_DIR/require-docker-runtime.sh"
# shellcheck source=docker.sh
source "$SCRIPT_DIR/docker.sh"

require_ubuntu_native_docker() {
    require_docker_runtime "$@"
}

main "$@"
