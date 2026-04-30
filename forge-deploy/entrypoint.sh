#!/bin/bash
set -e

# 执行权限修复
SOCKET_GID=$(stat -c '%g' /var/run/docker.sock)
if getent group docker > /dev/null 2>&1; then
    EXISTING_DOCKER_GID=$(getent group docker | cut -d: -f3)
    if [ "$EXISTING_DOCKER_GID" != "$SOCKET_GID" ]; then
        groupmod -g $SOCKET_GID docker
    fi
else
    groupadd -g $SOCKET_GID docker
fi

USER_ID=${PUID:-1000}
GROUP_ID=${PGID:-1000}
groupmod -o -g "$GROUP_ID" ubuntu
usermod -o -u "$USER_ID" -g "$GROUP_ID" ubuntu
usermod -aG docker ubuntu
chown -R ubuntu:ubuntu /home/ubuntu /workspace

# 克隆仓库
REPO_DIR="/workspace/forge"
if [ ! -d "$REPO_DIR/.git" ]; then
    rm -rf "$REPO_DIR"
    git clone https://github.com/WWFXL/Forge-AutoCompiler.git "$REPO_DIR"
fi
cd "$REPO_DIR"

# 安装依赖
make install

# 启动服务
exec gosu ubuntu make dev
