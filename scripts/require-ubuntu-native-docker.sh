#!/usr/bin/env bash

# Forge 的开发与正式实验固定使用 Ubuntu 发行版内的原生 Docker Engine。
# 本脚本只验证现状；不会启动服务、Docker Desktop 或修改 Docker 配置。

_forge_kernel_release() {
    cat /proc/sys/kernel/osrelease 2>/dev/null
}

_forge_command_exists() {
    command -v "$1" >/dev/null 2>&1
}

_forge_docker_service_state() {
    systemctl is-active docker 2>/dev/null
}

_forge_docker_service_pid() {
    systemctl show docker --property=MainPID --value 2>/dev/null
}

_forge_process_name() {
    cat "/proc/$1/comm" 2>/dev/null
}

_forge_docker_context() {
    docker context show 2>/dev/null
}

_forge_docker_endpoint() {
    docker context inspect default --format '{{.Endpoints.docker.Host}}' 2>/dev/null
}

_forge_docker_operating_system() {
    docker info --format '{{.OperatingSystem}}' 2>/dev/null
}

_forge_docker_socket_ready() {
    [ -S /var/run/docker.sock ]
}

_forge_docker_compose_ready() {
    docker compose version >/dev/null 2>&1
}

_forge_native_docker_error() {
    echo "ERROR: $1" >&2
    echo "Forge requires the native Docker Engine managed by systemd inside WSL2 Ubuntu." >&2
    echo "Do not start or switch to Docker Desktop. Ask the user to restore the Ubuntu Docker service, then rerun this check." >&2
    return 1
}

require_ubuntu_native_docker() {
    local kernel_release
    local service_state
    local service_pid
    local process_name
    local docker_context
    local docker_endpoint
    local docker_os
    local quiet=false

    if [ "${1:-}" = "--quiet" ]; then
        quiet=true
    elif [ "$#" -gt 0 ]; then
        _forge_native_docker_error "Unknown gate argument: $1"
        return 1
    fi

    kernel_release="$(_forge_kernel_release)"
    if [[ "${kernel_release,,}" != *microsoft* ]]; then
        _forge_native_docker_error "This command must run inside WSL2 Ubuntu."
        return 1
    fi
    if [ "${WSL_DISTRO_NAME:-}" != "Ubuntu" ]; then
        _forge_native_docker_error "WSL_DISTRO_NAME must be Ubuntu."
        return 1
    fi
    if [ -n "${DOCKER_HOST:-}" ] || [ -n "${DOCKER_CONTEXT:-}" ]; then
        _forge_native_docker_error "DOCKER_HOST and DOCKER_CONTEXT overrides are forbidden."
        return 1
    fi
    if ! _forge_command_exists docker || ! _forge_command_exists systemctl; then
        _forge_native_docker_error "docker and systemctl must be installed inside Ubuntu."
        return 1
    fi

    service_state="$(_forge_docker_service_state)"
    if [ "$service_state" != "active" ]; then
        _forge_native_docker_error "Ubuntu docker.service is not active."
        return 1
    fi
    service_pid="$(_forge_docker_service_pid)"
    if [[ ! "$service_pid" =~ ^[1-9][0-9]*$ ]]; then
        _forge_native_docker_error "Ubuntu docker.service has no live MainPID."
        return 1
    fi
    process_name="$(_forge_process_name "$service_pid")"
    if [ "$process_name" != "dockerd" ]; then
        _forge_native_docker_error "Ubuntu docker.service is not owned by dockerd."
        return 1
    fi

    docker_context="$(_forge_docker_context)"
    if [ "$docker_context" != "default" ]; then
        _forge_native_docker_error "Docker context must be default, not $docker_context."
        return 1
    fi
    docker_endpoint="$(_forge_docker_endpoint)"
    if [ "$docker_endpoint" != "unix:///var/run/docker.sock" ]; then
        _forge_native_docker_error "The default Docker endpoint must be unix:///var/run/docker.sock."
        return 1
    fi
    if ! _forge_docker_socket_ready; then
        _forge_native_docker_error "/var/run/docker.sock is not a Unix socket."
        return 1
    fi
    docker_os="$(_forge_docker_operating_system)"
    if [[ "$docker_os" != Ubuntu* ]]; then
        _forge_native_docker_error "Docker daemon operating system is not Ubuntu."
        return 1
    fi
    if ! _forge_docker_compose_ready; then
        _forge_native_docker_error "Docker Compose v2 is unavailable in Ubuntu."
        return 1
    fi

    if ! $quiet; then
        echo "OK: Forge Docker daemon provider=ubuntu-native; context=default; endpoint=/var/run/docker.sock"
    fi
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    require_ubuntu_native_docker "$@"
fi
