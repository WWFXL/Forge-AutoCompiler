# CLAUDE.md

本文件为 Claude Code（claude.ai/code）在本仓库工作时的总入口指南。子项目（`backend/`、`frontend/`）有更细的 CLAUDE.md，进入子目录工作时**优先读子目录的**。

## 1. 项目定位

**Forge-AutoCompiler** 是一个 C/C++ 仓库自动化编译系统。给一个 Git 仓库 URL，系统会：

1. 在 Docker 容器中创建隔离的编译会话
2. 把仓库 clone 进容器
3. 自动识别构建系统（CMake / Make / Autotools）
4. 由 **compiler 子代理**在容器内反复尝试 configure / build / 补依赖，直到产出可执行物
5. 把最终产物 `cp` 到 `/artifacts`
6. 系统对 `/artifacts` 做强制验证（exists / non-empty / smoke test `--version` 等）
7. 验证通过后生成 `repro/build.sh` 复现脚本，session 标记 completed

项目 fork 自 DeerFlow 2.0（一个通用 LangGraph Agent Harness）。许多 DeerFlow 时代的能力（IM channels、20+ skills、memory、MCP）**仍在代码中**，但**与编译核心无关**，是历史遗留。文档中明确标注 “非编译核心”，今后可能裁剪。

> **命名约定**：对外文档统一使用 **Forge-AutoCompiler**。Python 包名仍是 `deerflow.*`，仅作为内部实现细节出现。

## 2. 进程拓扑

`make dev` 拉起 4 个进程，通过 nginx 统一入口：

```
浏览器 → nginx :2026 ┬→ frontend (Next.js)   :3000   非 API 请求
                    ├→ gateway (FastAPI)     :8001   /api/*（models / skills / memory / uploads / threads / artifacts）
                    └→ langgraph server      :2024   /api/langgraph/*（agent 运行时）
```

**双运行模式**（仅启动方式不同，编译核心不变）：

- **标准模式** (`make dev`): LangGraph Server 作为独立进程跑 agent。4 个服务。
- **Gateway 模式** (`make dev-pro`，实验性): agent 运行时嵌进 Gateway（`backend/packages/harness/deerflow/runtime/`），nginx 把 `/api/langgraph/*` 改写到 Gateway，不需要 LangGraph Server。3 个服务。

完整的「dev/prod × 前台/守护进程 × 本机/Docker」矩阵见 [`backend/CLAUDE.md`](backend/CLAUDE.md)。

## 3. 常用命令（根目录）

```bash
make check          # 检查 node/pnpm/uv/nginx 是否就位
make config         # 首次生成 config.yaml（已存在则中止，非幂等）
make config-upgrade # 把 config.example.yaml 新增字段合并进现有 config.yaml
make install        # 安装前后端依赖（backend: uv sync，frontend: pnpm install）
make dev            # 启动全部服务，访问 http://localhost:2026
make dev-daemon     # 后台启动，日志写到 logs/*.log
make stop           # 停所有本机服务
make clean          # stop + 清空 backend/.deer-flow/、backend/.langgraph_api/、logs/
make docker-start   # Docker 开发环境（按 config.yaml 的 sandbox.mode 动态启动）
make up             # 生产 docker-compose
```

子项目命令分别看 [`backend/CLAUDE.md`](backend/CLAUDE.md) 和 [`frontend/CLAUDE.md`](frontend/CLAUDE.md)。

## 4. 编译核心（必读）

所有编译相关代码集中在 `backend/packages/harness/deerflow/compile/` 和与之配套的 agent / subagent / tool 文件。理解这部分才能改动产品逻辑。

### 4.1 模块布局

| 路径 | 职责 |
|---|---|
| `compile/schemas.py` | `CompileSession`、`BuildCommandRecord`、`BuildArtifact`、`VerificationResult`、`CommandResult` 等 dataclass |
| `compile/manager.py` | `CompileSessionManager`：创建/加载/保存 session、记录命令与产物、JSONL 事件日志 |
| `compile/operations.py` | 业务操作的 impl 入口：`prepare_compile_session_impl`、`clone_repository_impl`、`inspect_build_system_impl`、`submit_build_result_impl`、`finalize_compile_session_impl` |
| `compile/docker_runtime.py` | `CompileDockerRuntime`：容器创建/exec/拷贝/销毁，依赖 `HOST_PROJECT_ROOT` 环境变量 |
| `compile/paths.py` | host 路径与容器路径的命名/拼接 |
| `subagents/builtins/compiler_agent.py` | **compiler 子代理**的配置与系统提示词（核心契约文档） |
| `tools/builtins/agent_compile_tools.py` | Lead Agent 用的工具：`prepare_compile_session` / `clone_repository` / `identify_build_system` / `finalize_session` |
| `tools/bound_compile_tools.py` | compiler 子代理用的工具：`run_container_bash`、`submit_build_result` |

### 4.2 端到端工作流

```
Lead Agent
  ├─ prepare_compile_session(repo_url, branch?)
  │    → 创建 session、目录、Docker 容器（镜像 autocompiler:gcc13，network compile_network_wwf_v1）
  ├─ clone_repository()
  │    → git clone --depth 1 进容器的 /workspace/repo；记录 commit_sha；失败可重试
  ├─ identify_build_system()
  │    → 按 CMakeLists.txt / Makefile / configure 顺序探测
  ├─ task(subagent_type="compiler", prompt=...)
  │    → 委派给 compiler 子代理（迭代 build + submit_build_result）
  └─ finalize_session()
       → 停并删容器，session 状态置为 completed/failed
```

**compiler 子代理**：只有 `run_container_bash` 和 `submit_build_result` 两个工具，被禁止使用 `task` / `ask_clarification` / `view_image` 等。它必须：
- 失败时改策略，不允许盲目重试同一条命令
- 把最终产物 `cp`（而非 `mv`）到 `/artifacts`，不能整目录倾倒
- 跑 CMake 项目时若装了新 apt 包必须清掉 `build/`、`CMakeCache.txt`、`CMakeFiles/` 再 reconfigure
- 不允许自行宣告成功，必须以 `submit_build_result` 的返回为准
- 子代理返回严格 JSON：`{build_status, proceed_to_verify, verification_status, summary, artifacts[]}`

**验证（`submit_build_result_impl`）**：逐文件检查
1. `exists`：文件存在
2. `non_empty`：size > 0
3. 若是可执行：smoke test 依次尝试 `--version` / `-version` / `--help`，任一退出 0 即通过

全部通过 → session 状态 `completed`，自动生成 `repro/build.sh`（按记录的命令序列回放）。

### 4.3 会话目录布局（宿主机）

```
$HOST_PROJECT_ROOT/.compile-sessions/{thread_id}/{session_id}/
├── session.json             # CompileSession dataclass 的 JSON 持久化
├── workspace/repo/          # git clone 的目标
├── artifacts/               # 子代理 cp 的最终产物
├── logs/
│   ├── workflow.log         # JSONL 事件流（session.created、command.recorded、…）
│   ├── 001_clone.log        # 每条命令的 stdout+stderr 全量
│   └── ...
└── repro/build.sh           # 验证通过后生成的复现脚本
```

容器侧统一挂载到 `/workspace`、`/artifacts`、`/logs`、`/repro`。容器内仓库根永远是 `/workspace/repo`。

### 4.4 关键不变量（改动时勿破）

- **容器内仓库根永远是 `/workspace/repo`**：compiler 子代理、识别构建系统逻辑都强依赖这条
- **产物只看 `/artifacts`**：`submit_build_result_impl` 只列 `/artifacts` 下文件，不会去 build/ 找
- **`HOST_PROJECT_ROOT` 必须设置**：`CompileDockerRuntime._host_project_root()` 在缺失时会抛错
- **容器 network 固定 `compile_network_wwf_v1`**：若改名需同步 `RuntimeConfig.network`
- **smoke test 仅尝试 3 个旗标**：不要随便加，会污染验证语义
- **compiler 子代理的 system prompt 是产品契约**：改它等同于改产品行为，需要同时改 `compiler_agent.py` 和对应测试

## 5. 架构约束：Harness / App 分层

这是从 DeerFlow 继承下来的、**至今仍生效**的最重要架构不变量。

- **`backend/packages/harness/deerflow/`** 是可发布框架包（`deerflow-harness`，导入前缀 `deerflow.*`）。包含 agent 运行时、中间件、sandbox、tools、MCP、models、skills、config，以及**全部编译核心**。
- **`backend/app/`** 是不发布的应用层（导入前缀 `app.*`）。包含 FastAPI Gateway 路由和 IM 渠道桥接（Feishu/Slack/Telegram）。

**依赖方向**：`app` 可以导 `deerflow`；`deerflow` **严禁**导 `app`。由 `backend/tests/test_harness_boundary.py` 在 CI 强制；越线提交会直接挂。

新增能力时先问：这是「框架」（任何 harness 消费者都可能要）还是「应用」（仅 HTTP/IM）？前者放 `deerflow.*`，后者放 `app.*`。

## 6. 配置文件

两份文件都在项目根（gitignored，从 `*.example.*` 复制）：

- **`config.yaml`** — 模型、工具、tool groups、sandbox、memory、summarization、subagents、channels 等。有 `config_version` 字段（当前 `5`），schema 改动时在 `config.example.yaml` 里 +1，并提示用户跑 `make config-upgrade`。
- **`extensions_config.json`** — MCP 服务器和 skills 开关，可通过 Gateway API 运行时改。

值若以 `$` 开头按环境变量解析（如 `api_key: $OPENAI_API_KEY`）。

**加载顺序**（每个文件独立判断）：显式 `config_path` → `DEER_FLOW_CONFIG_PATH` / `DEER_FLOW_EXTENSIONS_CONFIG_PATH` 环境变量 → `backend/` 目录 → 项目根（**推荐**）。

`get_app_config()` 缓存结果，但比对路径和 mtime 自动重载，编辑 `config.yaml` 不需要重启 Gateway/LangGraph。

## 7. 项目状态快照（强制）

Stop hook（`~/.claude/hooks/snapshot.sh`）每次 session 调用过 `Edit`/`Write`/`Bash` 后注入提示，要求按本节维护 `<repo-root>/.claude/memory/project.md`。**违反本节会导致 hook 反复失败。**

### 文件路径（固定）

`/Users/yiwei/work1/Forge-AutoCompiler/.claude/memory/project.md`

### 必须的模块模板

文件不存在时**立即按此模板创建**，**不要询问用户**——hook 期望该文件存在，创建是默认动作而非可选项。

```markdown
# 项目状态快照 (Project State Snapshot)

跨 Claude Code session 的项目状态流水。按 CLAUDE.md §7 维护。

## 进行中 (In Progress)
<!-- 跨 session 未完成的工作。完成后挪到「最近变更」。 -->

## 最近变更 (Recent Changes)
<!-- 倒序，最新在上。 -->

## 待办 (TODOs)
<!-- 发现但未做的事。带 file:line 指针。 -->

## 已知问题 (Known Issues / Pitfalls)
<!-- 工作中踩过的坑、限制、规避方案。 -->
```

四个模块标题是**唯一允许**的一级章节，不要发明新章节。

### 何时写哪一节

| 本次 session 干了什么 | 模块 | 操作 |
|---|---|---|
| 实现功能 / 修 bug / 改配置 / 写新文件 | `## 最近变更` | 顶部 append 新条目 |
| 开了头但没收尾（被阻塞、延后等） | `## 进行中` | append；后续完成时移走 |
| 发现 TODO / 死代码 / 缺测试但未修 | `## 待办` | append，带 `file:line` |
| 撞上坑、限制或意外行为 | `## 已知问题` | append |
| 只读文件 / 跑 `git status` / 闲聊 | — | 写 `[snapshot:noop]`，不动文件 |

只改了 CLAUDE.md / README / ONBOARDING 之类**也算**状态变更，登记到「最近变更」。

### 条目格式

`## 最近变更` 下每条：

```markdown
- YYYY-MM-DD — <一句话总结，祈使句>
  - 文件: `path/to/a.py`, `path/to/b.tsx`
  - 动机: <为什么改>
```

日期写绝对 `YYYY-MM-DD`，会话中的「今天」「昨天」要换算（当前日期见系统上下文）。

### 哨兵 sentinel

回复末尾**恰好一个**：

- `[snapshot:done]` — 已 Read 文件（或按模板创建）、写完条目、保存。
- `[snapshot:noop]` — 本次 session 没有值得登记的状态变更。

hook 扫最近 5 条 assistant 消息找 sentinel，匹配到就不再触发。漏写 sentinel 会导致 hook 无限循环。

### 反模式

- ❌ 文件缺失时**问用户**要不要创建——直接按模板建
- ❌ 改过代码却写 `[snapshot:noop]`——`Edit`/`Write` 命中真实文件就是状态变更
- ❌ 发明新模块标题——只有四个固定的
- ❌ 写「今天」「昨天」——必须绝对日期
- ❌ 把已存在的条目再加一遍——先 Read，只 append 新内容

## 8. 提交前自检

CI（`.github/workflows/backend-unit-tests.yml`）每个 PR 跑 backend lint + pytest。本地对齐：

```bash
cd backend && make lint && make test
cd frontend && pnpm lint && pnpm typecheck
```

涉及 UI/env/auth/路由时还要：`cd frontend && BETTER_AUTH_SECRET=local-dev-secret pnpm build`。

## 9. 踩坑速查

- **`pnpm check` 是坏的**（`next lint` 解析到错路径），用 `pnpm lint && pnpm typecheck` 替代。
- **`pnpm build` 必须设 `BETTER_AUTH_SECRET`**——生产环境校验会拒掉默认值。`SKIP_ENV_VALIDATION=1` 只能压住校验，Better Auth 仍可能告警。
- **`make config` 非幂等**——检测到 `config.yaml` 直接 abort。升级用 `make config-upgrade`。
- **proxy env vars 会静默破坏 `pnpm install`**——前端装依赖报网络错时，先 unset `http_proxy`/`https_proxy`。
- **Docker Compose 里 IM channels 跑在 `gateway` 容器内**——`channels.langgraph_url`/`gateway_url` 写 `localhost` 会回环到容器自己。用 `http://langgraph:2024` / `http://gateway:8001`，或 `DEER_FLOW_CHANNELS_*_URL` 环境变量。
- **`HOST_PROJECT_ROOT` 没设容器创建会抛错**——本机起服务时通常由 `scripts/serve.sh` 注入；手动跑 backend 时要自己 export。

## 10. 已知废弃 / 非编译核心

下列内容**保留在代码中**，但**与编译流程无关**，不要据此推断产品定位：

- `main.py` 和根 `pyproject.toml`：早期残留 stub。`main.py` 只是 hello-world，根 `pyproject.toml` `dependencies = []`。真正入口在 `backend/`、`frontend/`。
- IM channels：`app/channels/`（Feishu/Slack/Telegram/WeCom）
- 通用 skills：`skills/public/` 下的 deep-research / image-generation / newsletter-generation 等，与编译无关
- memory 系统：`packages/harness/deerflow/agents/memory/`
- MCP 集成：`packages/harness/deerflow/mcp/`
- LangSmith / Langfuse tracing：可用但非必需

未来可能逐步裁剪，**不要主动把它们写进编译核心文档**。

## 11. 工作时去哪查

- 中间件链、Gateway router、内嵌客户端等 backend 细节 → [`backend/CLAUDE.md`](backend/CLAUDE.md)
- 前端线程流、artifacts UI、settings、env schema → [`frontend/CLAUDE.md`](frontend/CLAUDE.md)
- Docker compose 拓扑、宿主机资源建议 → [`CONTRIBUTING.md`](CONTRIBUTING.md)
- 给 coding agent 的引导式安装 → [`Install.md`](Install.md)
- 编译流程的更细机制说明 → [`docs/run_compile_workflow_workflow_mechanism.md`](docs/run_compile_workflow_workflow_mechanism.md)、[`docs/current_compile_project_implementation.md`](docs/current_compile_project_implementation.md)
- harness/app 分层细节 → [`backend/docs/HARNESS_APP_SPLIT.md`](backend/docs/HARNESS_APP_SPLIT.md)
- 中间件执行顺序的图解 → [`backend/docs/middleware-execution-flow.md`](backend/docs/middleware-execution-flow.md)
- 主配置字段表 → [`backend/docs/CONFIGURATION.md`](backend/docs/CONFIGURATION.md)（注：仍含 DeerFlow 时代措辞，按字段名为准）
