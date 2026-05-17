# Forge-AutoCompiler Copilot 上手指南

本文件是 coding agent（Copilot / Cursor / Codex / Claude Code 等）在本仓库工作时的**默认操作手册**。先读这里，只有本文件信息不全或与现实矛盾时再去搜代码。

## 1. 项目摘要

Forge-AutoCompiler 是面向 C/C++ 仓库的自动化编译系统：

- **后端**：Python 3.12，LangGraph 编排 + FastAPI 网关，编译核心在 `backend/packages/harness/deerflow/compile/`
- **前端**：Next.js 16 + React 19 + TypeScript + pnpm
- **本机入口**：根 `Makefile`，`make dev` 把 LangGraph + Gateway + Frontend + nginx 起在 `http://localhost:2026`
- **Docker 入口**：`make docker-*`，按 `config.yaml` 的 sandbox.mode 决定是否启动 provisioner

仓库规模中等偏大：后端服务 + 前端应用 + Docker 编排 + skills 库 + 文档。

> 命名：项目对外叫 **Forge-AutoCompiler**。代码内 Python 包名 `deerflow.*` 是历史遗留（从 DeerFlow 2.0 fork），仅作内部实现细节。

## 2. 工具链要求

在 macOS 上已验证：

- Node.js `>=22`（验证：23.11.0）
- pnpm `10.26.2`+（项目锁死在 10）
- Python `>=3.12`（CI 用 3.12）
- `uv` `0.7.20`+
- nginx（`make dev` 统一入口需要）
- Docker（编译容器需要）

**所有命令默认从仓库根执行**，除非命令明确说从子目录跑。

## 3. 已验证的命令序列

### A. Bootstrap

```bash
make check    # 校验前置工具
make install  # 装前后端依赖（backend: uv sync，frontend: pnpm install）
```

### B. 后端 CI 等价校验

从 `backend/` 跑：

```bash
make lint   # ruff check + ruff format --check
make test   # PYTHONPATH=. uv run pytest tests/ -v
```

CI（`.github/workflows/backend-unit-tests.yml`）在 PR 上跑：`uv sync --group dev` → `make lint` → `make test`。

### C. 前端校验

从 `frontend/` 跑，**推荐**序列：

```bash
pnpm lint
pnpm typecheck
BETTER_AUTH_SECRET=local-dev-secret pnpm build
```

**已知失败模式**：

- `pnpm build` 不设 `BETTER_AUTH_SECRET` 会被生产 env 校验拒掉。最佳：设真实值；次选：`SKIP_ENV_VALIDATION=1`，但 Better Auth 仍可能告警。
- **`pnpm check` 是坏的**（`next lint` 解析到错路径），不要依赖。分开跑 `pnpm lint && pnpm typecheck`。

### D. 本地跑全栈

```bash
make dev       # 前台
make stop      # 停
```

行为：

- 启动前先停旧服务
- 拉起 LangGraph (2024) / Gateway (8001) / Frontend (3000) / nginx (2026)
- 统一访问点 `http://localhost:2026`
- 日志：`logs/{langgraph,gateway,frontend,nginx}.log`

工具会话超时打断了 `make dev`？再跑一次 `make stop` 确保清理。

### E. 配置 bootstrap

```bash
make config
```

**重要行为**：

- 若 `config.yaml`（或 `config.yml` / `configure.yml`）已存在，**主动 abort**。
- 仅用于干净 clone 后的首次配置。升级用 `make config-upgrade`。

## 4. 推荐命令顺序（最少踩坑）

针对本机代码改动：

1. `make check`
2. `make install`（前端拉依赖失败时 unset proxy 重试）
3. 后端：`cd backend && make lint && make test`
4. 前端：`cd frontend && pnpm lint && pnpm typecheck`
5. 涉及 UI/env/auth/路由：`BETTER_AUTH_SECRET=... pnpm build`

PR 前必跑后端 lint 和 test——CI 强制。

## 5. 关键路径

### 顶层编排与配置

- `Makefile` — 本机/Docker 命令总入口
- `config.example.yaml` — 主配置模板
- `config.yaml` — 本地激活配置（gitignored）
- `docker/docker-compose-dev.yaml` — Docker dev 拓扑
- `.github/workflows/backend-unit-tests.yml` — PR 校验流水线

### 后端

- `backend/packages/harness/deerflow/compile/` — **★ 编译核心**
  - `schemas.py` — CompileSession 等 dataclass
  - `manager.py` — 会话生命周期 + JSONL 事件日志
  - `operations.py` — prepare/clone/inspect/submit/finalize 业务 impl
  - `docker_runtime.py` — 容器创建/exec/拷贝/销毁
  - `paths.py` — 宿主机/容器路径命名
- `backend/packages/harness/deerflow/subagents/builtins/compiler_agent.py` — **★ compiler 子代理契约**
- `backend/packages/harness/deerflow/tools/builtins/agent_compile_tools.py` — Lead Agent 用的工具
- `backend/packages/harness/deerflow/tools/bound_compile_tools.py` — compiler 子代理用的工具
- `backend/packages/harness/deerflow/agents/lead_agent/` — Lead Agent 工厂 + prompt
- `backend/app/gateway/` — FastAPI 网关
- `backend/langgraph.json` — LangGraph 入口（`deerflow.agents:make_lead_agent`）
- `backend/tests/` — pytest 测试

### 前端

- `frontend/src/app/` — Next.js 路由
- `frontend/src/components/workspace/welcome.tsx` — Forge Welcome / Hero / Action Cards
- `frontend/src/core/` — 业务逻辑（threads / api / artifacts / messages / settings / skills / mcp / memory / models / i18n）
- `frontend/src/env.js` — env schema 校验（影响 `pnpm build`）

## 6. 提交前期望

至少跑：

```bash
cd backend && make lint && make test
cd frontend && pnpm lint && pnpm typecheck
```

涉及 UI/env/auth 时：

```bash
cd frontend && BETTER_AUTH_SECRET=... pnpm build
```

涉及编排或配置（`Makefile`、`docker/*`、`config*.yaml`）时还要 `make dev` 验证 4 个服务能起来。

## 7. 非显然的踩坑

- **proxy 环境变量**会静默破坏前端网络操作（`pnpm install` / 注册表）
- **`BETTER_AUTH_SECRET`** 实际上是前端生产构建必需
- Next.js 可能告警多个 lockfile / workspace root 推断——目前只是 warning，不阻塞构建
- **`make config` 非幂等**——已存在配置时直接 abort
- **`make dev`** 包含进程清理逻辑，被打断时日志会有 shutdown 噪声，属正常
- **`HOST_PROJECT_ROOT` 必须设置**——本机模式由 `scripts/serve.sh` 注入，手动跑 backend 时必须自己 export

## 8. 根级清单速查

- `.github/` — workflows、本指南
- `backend/` — Python 后端
- `frontend/` — Next.js 前端
- `docker/` — compose / nginx 配置
- `skills/` — agent skills 库（多数与编译无关）
- `scripts/` — 启动、检查、部署
- `docs/` — 项目文档
- `README_zh.md` — 中文 README（主）
- `CONTRIBUTING.md` — 贡献指南
- `CLAUDE.md` — Claude Code 总指南
- `Install.md` — 给 coding agent 的引导式安装
- `Makefile` — 命令总入口
- `config.example.yaml` — 主配置模板
- `extensions_config.example.json` — MCP / Skills 配置模板

## 9. 指令优先级

**优先信任本指南。**

只有以下情况才做广义代码搜索（`grep` / `find` / code search）：

- 需要本指南未覆盖的文件级实现细节
- 本指南里的某条命令失败，需要更新的替代行为
- CI / workflow 定义在本指南撰写后改了

## 10. 文档地图

- 给 Claude Code 看的总指南 → [`CLAUDE.md`](../CLAUDE.md)
- 后端实现 → [`backend/CLAUDE.md`](../backend/CLAUDE.md)
- 前端实现 → [`frontend/CLAUDE.md`](../frontend/CLAUDE.md)
- 公开介绍 → [`README_zh.md`](../README_zh.md)
- 安装手册 → [`Install.md`](../Install.md)
- 贡献流程 → [`CONTRIBUTING.md`](../CONTRIBUTING.md)
- 编译流程机制 → [`docs/run_compile_workflow_workflow_mechanism.md`](../docs/run_compile_workflow_workflow_mechanism.md)
- 现状自审 → [`docs/current_compile_project_implementation.md`](../docs/current_compile_project_implementation.md)
