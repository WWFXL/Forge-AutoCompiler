# 贡献指南

感谢你愿意为 Forge-AutoCompiler 贡献代码！本文档说明开发环境搭建和工作流程。

## 开发环境

我们提供两种开发环境，**推荐 Docker**——一致、隔离、不污染本机。

### 方案一：Docker 开发（推荐）

#### 前置

- Docker Desktop 或 Docker Engine
- pnpm（用于宿主机侧缓存共享，加速构建）

#### 步骤

1. **配置**：
   ```bash
   make config         # 首次生成 config.yaml
   # 编辑 config.yaml，至少配置一个 LLM 模型
   export OPENAI_API_KEY="..."   # 或对应你模型的 key
   ```

2. **初始化 Docker 环境**（首次）：
   ```bash
   make docker-init
   ```
   会构建镜像、安装前后端依赖、共享 pnpm 缓存。

3. **启动**：
   ```bash
   make docker-start
   ```
   `make docker-start` 会读 `config.yaml`，只在 sandbox mode 是 provisioner/Kubernetes 时才起 `provisioner` 容器。

   所有服务 hot-reload：
   - 前端：自动刷新
   - 后端：代码改动自动重启
   - LangGraph：支持 hot-reload

4. **访问**：
   - Web 界面：http://localhost:2026
   - Gateway API：http://localhost:2026/api/*
   - LangGraph：http://localhost:2026/api/langgraph/*

#### Docker 常用命令

```bash
make docker-init             # 构建/初始化（首次或镜像变更后）
make docker-start            # 启动开发服务
make docker-stop             # 停服务
make docker-logs             # 查看全部日志
make docker-logs-frontend    # 仅前端日志
make docker-logs-gateway     # 仅 Gateway 日志
```

构建慢时可以预先设置包源：

```bash
export UV_INDEX_URL=https://pypi.org/simple
export NPM_REGISTRY=https://registry.npmjs.org
```

#### 推荐资源

| 场景 | 起步 | 推荐 | 说明 |
|---|---|---|---|
| `make dev` 单机开发 | 4 vCPU / 8GB | 8 vCPU / 16GB | 使用托管 LLM API 时足够 |
| `make docker-start` 评审环境 | 4 vCPU / 8GB | 8 vCPU / 16GB | Docker 镜像与编译容器需要余量 |
| 共用 Linux 测试服 | 8 vCPU / 16GB | 16 vCPU / 32GB | 多并发编译/多评审人 |

`2 vCPU / 4GB` 常常起不来或在正常负载下卡死，请避免。

#### Linux：Docker daemon 权限被拒

如果 `make docker-*` 报：

```
unable to get image 'deer-flow-dev-langgraph': permission denied while trying to connect to the Docker daemon socket at unix:///var/run/docker.sock
```

把当前用户加进 `docker` 组：

```bash
getent group docker
sudo usermod -aG docker $USER
newgrp docker         # 或者完整退登重登
docker ps             # 验证
```

### 方案二：本机原生开发

需要：
- Node.js 22+
- pnpm 10.26.2+
- Python 3.12+ 与 [`uv`](https://docs.astral.sh/uv/)
- nginx
- Docker（编译容器需要）

```bash
make check        # 校验前置工具
make install      # 装前后端依赖
# 编辑 config.yaml，配置至少一个模型
make dev          # 启动全部服务，访问 http://localhost:2026
```

需要分进程启动时：

```bash
# Terminal 1：LangGraph
cd backend && make dev

# Terminal 2：Gateway
cd backend && make gateway

# Terminal 3：Frontend
cd frontend && pnpm dev

# Terminal 4：nginx
make nginx
# 或 nginx -c $(pwd)/docker/nginx/nginx.local.conf -g 'daemon off;'
```

**手动跑 backend 时必须 export `HOST_PROJECT_ROOT`**，否则 `CompileDockerRuntime` 会拒绝创建编译容器。

## 开发流程

1. **建分支**：
   ```bash
   git checkout -b feature/your-feature
   ```

2. **改代码**，享受 hot-reload。

3. **格式化与 lint**（CI 会拒绝未格式化代码）：
   ```bash
   # 后端
   cd backend && make format

   # 前端
   cd frontend && pnpm format:write
   ```

4. **跑测试**：
   ```bash
   cd backend && make test
   cd frontend && pnpm lint && pnpm typecheck
   ```
   涉及 UI/env/auth/路由变更时还要：
   ```bash
   cd frontend && BETTER_AUTH_SECRET=local-dev-secret pnpm build
   ```

5. **提交**：
   ```bash
   git add -p
   git commit -m "feat: 描述你的改动"
   ```

6. **PR**：推上去开 Pull Request。CI 会自动跑 `.github/workflows/backend-unit-tests.yml`：`uv sync --group dev` → `make lint` → `make test`。

### Commit 风格

参考最近 commit 历史：

- `feat(scope): ...` 新功能
- `fix(scope): ...` Bug 修复
- `refactor(scope): ...` 重构
- `docs: ...` 文档
- `test: ...` 测试

## 编译核心改动须知

如果你要动 `backend/packages/harness/deerflow/compile/` 下的代码或 compiler 子代理：

- **`compiler_agent.py` 的 system prompt 是产品契约**，改它等同于改产品行为。务必同步改 `tests/test_compile_runtime.py`。
- **路径常量双重维护**：宿主机路径在 `compile/paths.py`，容器路径在 `compile/docker_runtime.py` 顶部常量。改一边要改另一边。
- **新增编译阶段**必须沿用 `append_command_record()`，否则 `repro/build.sh` 复现脚本会缺步骤。
- **状态机变更**（`CompileSession.status`）要更新 `logs/workflow.log` 的事件命名约定。

## 架构约束

最关键不变量：

**`backend/packages/harness/deerflow/` 不能 import `app.*`**。

由 `backend/tests/test_harness_boundary.py` 在 CI 强制。越线提交会直接挂。详细规则见 [`backend/docs/HARNESS_APP_SPLIT.md`](backend/docs/HARNESS_APP_SPLIT.md)。

## 代码风格

| 子项目 | 工具 | 提交前命令 |
|---|---|---|
| 后端（Python） | `ruff` | `make format` |
| 前端（TypeScript） | ESLint + Prettier | `pnpm format:write` |

CI 强制校验格式，未格式化的 PR 直接挂在 lint 阶段。

## 跟进与提问

- 看现有 [Issues](../../issues)
- 看现有 [Discussions](../../discussions)
- 看 [`CLAUDE.md`](CLAUDE.md) 了解架构与工作流

## 协议

提交的贡献按 [MIT License](./LICENSE) 授权。
