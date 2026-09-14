#!/usr/bin/env bash

# Forge 的通用 Docker 工作流只依赖可访问的 daemon、Compose 和 DooD socket。
# 本脚本只验证现状，不启动服务或修改 Docker 配置。

_forge_command_exists() {
    command -v "$1" >/dev/null 2>&1
}

_forge_docker_daemon_ready() {
    docker info >/dev/null 2>&1
}

_forge_docker_socket_ready() {
    [ -S /var/run/docker.sock ]
}

_forge_docker_compose_ready() {
    docker compose version >/dev/null 2>&1
}

_forge_docker_runtime_error() {
    echo "ERROR: $1" >&2
    echo "Forge requires a reachable Docker daemon, Docker Compose, and /var/run/docker.sock." >&2
    return 1
}

require_docker_runtime() {
    local quiet=false

    if [ "${1:-}" = "--quiet" ]; then
        quiet=true
    elif [ "$#" -gt 0 ]; then
        _forge_docker_runtime_error "Unknown gate argument: $1"
        return 1
    fi

    if ! _forge_command_exists docker; then
        _forge_docker_runtime_error "The docker command is unavailable."
        return 1
    fi
    if ! _forge_docker_daemon_ready; then
        _forge_docker_runtime_error "The Docker daemon is unreachable."
        return 1
    fi
    if ! _forge_docker_socket_ready; then
        _forge_docker_runtime_error "/var/run/docker.sock is unavailable."
        return 1
    fi
    if ! _forge_docker_compose_ready; then
        _forge_docker_runtime_error "Docker Compose is unavailable."
        return 1
    fi

    if ! $quiet; then
        echo "OK: Forge Docker runtime is ready."
    fi
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    require_docker_runtime "$@"
fi
