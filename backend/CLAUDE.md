# backend/CLAUDE.md

本文件是 Forge-AutoCompiler 后端的工作指南。**先读根目录的 [`/CLAUDE.md`](../CLAUDE.md)**，了解整体定位、双进程拓扑、编译核心契约、项目状态快照规则。本文件聚焦后端实现细节。

## 1. 模块布局

```
backend/
├── Makefile                          # 后端独立命令（dev / gateway / test / lint / format）
├── pyproject.toml                    # uv workspace 主 manifest，把 deerflow-harness 作为 workspace 成员
├── langgraph.json                    # LangGraph CLI 配置，入口 deerflow.agents:make_lead_agent
├── ruff.toml                         # 行宽 240，双引号
├── debug.py                          # 一次性调试脚本
├── app/                              # 应用层（import: app.*）— 不发布
│   ├── gateway/                      # FastAPI 网关
│   │   ├── app.py                    # FastAPI 实例
│   │   └── routers/                  # 路由模块（models / mcp / memory / skills / uploads / threads / artifacts / suggestions / agents / channels）
│   └── channels/                     # IM 桥接（Feishu/Slack/Telegram/WeCom）— 非编译核心
├── packages/harness/                 # 框架包 deerflow-harness（import: deerflow.*）— 可独立发布
│   └── deerflow/
│       ├── agents/                   # LangGraph agent 系统
│       │   ├── lead_agent/           # Lead agent 工厂 + prompt
│       │   ├── middlewares/          # 中间件实现
│       │   ├── memory/               # memory 抽取与队列（非编译核心）
│       │   ├── checkpointer/         # AsyncSqliteSaver provider
│       │   └── thread_state.py       # ThreadState schema
│       ├── compile/                  # ★ 编译核心
│       │   ├── schemas.py            # CompileSession 等 dataclass
│       │   ├── manager.py            # 会话生命周期、JSONL 事件日志
│       │   ├── operations.py         # prepare/clone/inspect/submit/finalize 业务 impl
│       │   ├── docker_runtime.py     # 容器创建/exec/拷贝/销毁
│       │   └── paths.py              # 宿主机/容器路径命名
│       ├── subagents/
│       │   ├── builtins/             # general_purpose / bash / compiler
│       │   ├── executor.py           # 子代理后台执行
│       │   └── registry.py           # 子代理注册表
│       ├── tools/
│       │   ├── builtins/             # agent_compile_tools / clarification_tool / present_file_tool / setup_agent_tool / task_tool / tool_search / view_image_tool
│       │   └── bound_compile_tools.py  # ★ compiler 子代理专用工具
│       ├── sandbox/                  # 抽象 Sandbox interface 与本地 provider
│       ├── mcp/                      # MCP 集成（非编译核心）
│       ├── models/                   # ChatModel 工厂、vLLM provider 等
│       ├── skills/                   # SKILL.md 发现与加载
│       ├── config/                   # 配置系统（app/agents/models/sandbox/subagents/summarization/paths）
│       ├── community/                # 社区工具（tavily/jina/firecrawl/image_search）— 非编译核心
│       ├── reflection/               # 动态模块加载（resolve_variable / resolve_class）
│       ├── runtime/                  # Gateway 模式下的嵌入式运行时（RunManager/StreamBridge）
│       └── client.py                 # DeerFlowClient：进程内嵌入式客户端
├── tests/                            # pytest 测试
└── docs/                             # 后端文档（多数已清理，仅保留 HARNESS_APP_SPLIT / middleware-execution-flow / CONFIGURATION / SETUP）
```

## 2. 编译核心实现细节

总流程已在 [`/CLAUDE.md` §4](../CLAUDE.md#4-编译核心必读) 描述。下面是后端实现层面的额外要点。

### 2.1 状态机

`CompileSession.status` 取值：

```
created → ready → source_ready → inspected → (compiler 子代理执行) → verified → completed
                                                                    ↘ verification_failed
任意非终态 ────────────────────────────────────────────────────────→ failed / cancelled / timed_out
```

- `created`：`prepare_compile_session_impl` 创建 session 但未起容器
- `ready`：容器起来了
- `source_ready`：clone 成功
- `inspected`：识别完构建系统
- `verified`：`submit_build_result` 的原始产物检查、commit-pinned 候选 bundle 和自动 clean replay 比较均通过；此时 `completed_at` 仍为空
- `completed`：已验证 session 的编译容器清理成功，并由 finalize 写入终态
- `verification_failed`：`submit_build_result` 验证失败（产物无效、smoke 失败、候选 bundle 无法安全生成、clean replay 执行/比较失败或 replay 容器清理失败）
- `failed`：clone 失败或其他不可恢复错误

每次状态切换都会写一条 `session.status_changed` 事件进 `logs/workflow.log`，**改状态机时务必同步事件日志的语义**。

### 2.2 命令记录

`session.commands` 是完整的命令审计轨迹。clone、inspect 和 `run_container_bash` 等阶段会记录：

- 记录到 `session.commands`（持久化到 `session.json`）
- 写一份完整 stdout+stderr 到独立 log（命名 `{index:03d}_{stage}.log`）
- `workflow.log` 写一条 `command.recorded` JSONL 事件

`submit_build_result` 是验证/审计事件：它写 `submit.*` 事件、summary log 和 verification checks，但不伪装成 shell command 写入 `session.commands`。

成功 submit 时生成 `repro/build.sh`。生成器只消费 `stage == "bash" && exit_code == 0` 的记录，保持顺序与各自容器 `workdir`，并用独立 `bash -lc` 执行。clone/inspect、失败或超时尝试以及 submit 审计均不进入 replay。

需要进入 replay 的构建步骤必须通过 `run_container_bash` 执行；`workdir` 必须是 `/workspace` 或 `/artifacts` 下的绝对容器路径。生成器还要求完整 40/64 位 commit SHA、无持久凭据的远端 URL，并拒绝 Windows/WSL 宿主路径、`.compile-sessions` 路径和 session 标识。修改过滤或安全规则时必须同步 `tests/test_compile_runtime.py`。

`repro_bundle` verification check 只证明候选脚本可安全生成且非空。随后 `submit_build_result` 自动用 session 保存的完整 `image_id` 创建唯一 `replay/<attempt_id>/`，把候选脚本复制到只读 recipe mount，并从空 workspace/artifacts 执行。原容器的 tag 仅作说明，replay 不得重新解析它；`image_id` 只保证同一 Docker daemon 内的精确镜像身份。

每个 replay attempt 独立持久化实际 timeout、执行日志、duration、image identity、failure classification，以及原始/replay 产物的相对路径集合、类型、大小、SHA-256、smoke 命令、退出码、有限预览和完整输出 SHA-256。只有执行、全部比较和容器清理均成功才能把 session 标为 `verified`；删除原 compile container 后还要重新核对最终产物集合、类型、大小和 SHA-256，才能标为 `completed`。执行/验证 deadline 来自 `COMPILE_REPLAY_TIMEOUT_SECONDS`（默认 `1200` 秒），覆盖 Docker control 与本地 artifact 工作；cleanup 使用独立短时限。创建握手必须在 session lock 内完成，父任务取消在 worker 停止前后都要重新加载并按 name/ID 幂等清理，worker 不得用 stale session 覆盖 `cancelled`。Replay 目录不得与原 workspace/artifacts 重合，容器不得继承模型凭据。

### 2.3 路径双重映射

宿主机路径与容器路径在两层维护：

- **Python 层视角**：`compile/paths.py` 给出宿主机绝对路径（`get_session_dir`、`get_workspace_dir` 等）
- **容器视角**：固定 `/workspace/repo`、`/artifacts`、`/logs`、`/repro`

自动 replay 还维护服务进程可见与 Docker daemon 可见的两套 `replay/<attempt_id>/{recipe,workspace,artifacts,logs}` 路径。Docker-in-Docker-out 模式必须从 host-path helper 取得 bind source，不能把 backend 容器内普通 `tempfile` 路径直接交给宿主 daemon。

`CompileDockerRuntime` 在 `create_container()` 把宿主机路径以 `-v` 挂进容器，挂载点由 `docker_runtime.py` 顶部常量定义（`CONTAINER_WORKSPACE_DIR` 等）。**改任何一边的路径都要同步另一边**。

### 2.4 子代理工具集

| 工具 | 调用者 | 实现 |
|---|---|---|
| `prepare_compile_session` | Lead Agent | `tools/builtins/agent_compile_tools.py` |
| `clone_repository` | Lead Agent | 同上 |
| `identify_build_system` | Lead Agent | 同上 |
| `finalize_session` | Lead Agent | 同上 |
| `run_container_bash` | compiler 子代理 | `tools/bound_compile_tools.py` |
| `submit_build_result` | compiler 子代理 | 同上（内部调 `submit_build_result_impl`） |

compiler 子代理通过 `disallowed_tools` 明确禁掉 `task` / `ask_clarification` / `present_files` / `view_image` 等，避免它跳出编译职责。

### 2.5 关键测试

- `tests/test_compile_runtime.py`：CompileSessionManager / DockerRuntime / 工具行为的单测
- `tests/test_harness_boundary.py`：harness → app 导入防火墙（CI 必跑）

新增编译能力时**至少**要给 `compile_runtime` 那块加 case。

## 3. Lead Agent 与中间件

入口 `deerflow.agents:make_lead_agent`（注册在 `backend/langgraph.json`），代码在 `packages/harness/deerflow/agents/lead_agent/agent.py`。

### 3.1 当前实际中间件

按代码导入和注册顺序：

1. **`build_lead_runtime_middlewares(...)`** — tool error handling 系列
2. **`SummarizationMiddleware`** — 上下文摘要（可选，按配置）
3. **`TodoMiddleware`** — Plan 模式 TodoList（仅 `is_plan_mode=True`）
4. **`TitleMiddleware`** — 自动生成会话标题
5. **`MemoryMiddleware`** — 异步 memory 抽取队列（非编译核心，可关）
6. **`ViewImageMiddleware`** — 视觉模型图片注入（按模型能力开启）
7. **`SubagentLimitMiddleware`** — 截断超额 `task` 工具调用
8. **`LoopDetectionMiddleware`** — 循环检测
9. **`TokenUsageMiddleware`** — token 用量计数（按 `token_usage.enabled`）
10. **`ClarificationMiddleware`** — 拦截 `ask_clarification`，`Command(goto=END)`（必须最后）

> ⚠️ 如果你看到旧文档（已删除）写「9 个 / 10 个中间件 + ThreadDataMiddleware / SandboxMiddleware / DanglingToolCallMiddleware / GuardrailMiddleware / UploadsMiddleware」——那是 DeerFlow 时期的清单，已不准确。以本节为准；以源码为最终真相。

### 3.2 Prompt 注意

`lead_agent/prompt.py` 顶部注释明确：

> Detailed repository-compilation workflow knowledge intentionally lives in the compiler subagent prompt instead of the lead prompt.

Lead Agent 的提示词刻意**不**把详细编译流程写进去，避免污染非编译会话。详细规则集中在 `subagents/builtins/compiler_agent.py` 的 system_prompt。改产品行为时通常是改后者，而非 lead prompt。

### 3.3 Runtime configurable

通过 `config.configurable` 传入：

- `thinking_enabled`：扩展思考
- `model_name`：选用具体 LLM
- `is_plan_mode`：启用 TodoMiddleware
- `subagent_enabled`：是否暴露 `task` 工具
- `thread_id`：贯穿 ThreadState

## 4. Gateway API

`app/gateway/app.py` 是 FastAPI 入口，端口 8001，`GET /health` 健康检查。

**路由总览**（以源码 `app/gateway/routers/` 为准）：

| 路由 | 主要端点 |
|---|---|
| `/api/models` | `GET /`、`GET /{name}` |
| `/api/mcp` | `GET /config`、`PUT /config` |
| `/api/skills` | `GET /`、`GET /{name}`、`PUT /{name}`、`POST /install` |
| `/api/memory` | `GET /`、`POST /reload`、`GET /config`、`GET /status` |
| `/api/threads/{id}/uploads` | `POST /`、`GET /list`、`DELETE /{filename}` |
| `/api/threads/{id}` | `DELETE /` |
| `/api/threads/{id}/artifacts/{path}` | `GET /` |
| `/api/threads/{id}/suggestions` | `POST /` |
| `/api/agents` | 暴露子代理元数据 |
| `/api/channels` | IM 渠道状态（非编译核心） |

**注意**：Gateway 当前**没有专门的编译路由**。编译流程通过 LangGraph 的 thread/run/messages 协议触发——前端把 `compile <repo_url>` 类指令发给 agent，agent 自己决定调 `prepare_compile_session` 等工具。如果将来要加 `POST /api/compile`，需要在 Gateway 起一个新 router。

## 5. 配置加载

`config.yaml`（项目根，gitignored）由 `packages/harness/deerflow/config/app_config.py` 加载。

- 第一次启动后 `get_app_config()` 缓存
- 文件路径变化或 mtime 变大时自动重载（无需重启）
- `config_version` 当前 6；schema 改时在 `config.example.yaml` +1，用户跑 `make config-upgrade` 自动合并
- `$VAR` 占位符在加载时被环境变量替换

关键段落与其消费者：

| 段 | 消费者 |
|---|---|
| `models[]` | `deerflow.models.factory.create_chat_model` |
| `tools[]` / `tool_groups[]` | `deerflow.tools.builtins.tool_search`、Lead Agent `get_available_tools` |
| `sandbox` | v6 兼容字段，应为 `null`；C/C++ 构建隔离由 `deerflow.compile` 管理 |
| `memory` | `deerflow.agents.memory.*` |
| `summarization` | Lead Agent 中的 `SummarizationMiddleware` |
| `subagents` | `deerflow.subagents.config` |
| `title` | `TitleMiddleware` |
| `channels` | `app/channels/service.py` |

字段完整表见 [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md)（注：仍含 DeerFlow 措辞，以字段名为准）。

## 6. 命令

```bash
make install    # uv sync
make dev        # langgraph dev --no-browser --no-reload --n-jobs-per-worker 10（端口 2024）
make gateway    # uvicorn app.gateway.app:app --host 0.0.0.0 --port 8001
make test       # PYTHONPATH=. uv run pytest tests/ -v
make lint       # ruff check . + ruff format --check .
make format     # ruff check . --fix + ruff format .

# 单跑一个测试
PYTHONPATH=. uv run pytest tests/test_compile_runtime.py -v
PYTHONPATH=. uv run pytest tests/test_compile_runtime.py::test_session_manager_create -v
```

CI 在 `.github/workflows/backend-unit-tests.yml`，每个 PR 都跑 `uv sync --group dev` → `make lint` → `make test`。

## 7. Harness / App 边界

**`packages/harness/deerflow/` 不能 import `app.*`**。`tests/test_harness_boundary.py` 在 CI 强制。

```python
# ✓ 允许：app 用 harness
from deerflow.compile.operations import prepare_compile_session_impl

# ✓ 允许：harness 内部
from deerflow.subagents import get_available_subagent_names

# ✗ 禁止：harness 反向依赖 app（CI 会挂）
# from app.gateway.routers.uploads import ...
```

更详细的边界规则见 [`docs/HARNESS_APP_SPLIT.md`](docs/HARNESS_APP_SPLIT.md)。

## 8. 内嵌客户端 `DeerFlowClient`

`packages/harness/deerflow/client.py` 提供进程内 API，不依赖 LangGraph Server 和 FastAPI，可以在脚本、notebook、其他 Python 服务里直接调编译流程。返回类型与 Gateway API 的响应模型对齐（`TestGatewayConformance` 在 `tests/test_client.py` 强制校验）。

主要方法：
- `chat(message, thread_id)` / `stream(message, thread_id)` — 同步 agent 对话
- `astream(message, thread_id)` — 原生异步事件流；包含 async-only 工具的 embedded runner 必须使用此路径
- 编译相关：通过 chat 走完整 agent 流程（与 Gateway 一致）
- 配置：`list_models()` / `get_model(name)` / `list_skills()` / `update_skill()` / `get_mcp_config()` / `update_mcp_config()`
- 文件：`upload_files(thread_id, files)` / `list_uploads(thread_id)` / `delete_upload(thread_id, filename)` / `get_artifact(thread_id, path)`
- 内存：`get_memory()` / `reload_memory()` / `get_memory_config()` / `get_memory_status()`

`update_skill()` / `update_mcp_config()` 会自动失效缓存的 agent。

## 9. 容器与 sandbox

历史上 DeerFlow 有一个抽象 `Sandbox` 系统，目前**仍在代码里**，主要用于：

- Local sandbox（直接读写 `backend/.deer-flow/threads/{thread_id}/...`）
- Aio sandbox（已在 `b47fd909` 移除，留下抽象接口）

**编译流程不走 Sandbox 抽象**，它有自己的 `CompileDockerRuntime`。Sandbox 主要服务于通用 chat 场景（文件预览、上传文件读取等），与编译核心解耦。

最新动向：`sandbox` 配置已可选（commit `2166c8b9`），sandbox 完全关掉也能跑。

## 10. 不要相信的旧文档

代码里和 git 历史里仍有 DeerFlow 2.0 时期的描述。**以源码为准**。**已删除**但你可能在 git 历史中看到的：

- `backend/docs/ARCHITECTURE.md`（描述老中间件链）
- `backend/docs/API.md`、`backend/docs/README.md`、`backend/docs/FILE_UPLOAD.md` 等
- 所有 `rfc-*.md`
- `MEMORY_IMPROVEMENTS*.md`、`AUTO_TITLE_GENERATION.md`、`TITLE_GENERATION_IMPLEMENTATION.md`
- `MCP_SERVER.md` / `GUARDRAILS.md` / `APPLE_CONTAINER.md` / `plan_mode_usage.md` / `summarization.md` / `task_tool_improvements.md` / `TODO.md` / `PATH_EXAMPLES.md`

保留下来的是：`HARNESS_APP_SPLIT.md`、`middleware-execution-flow.md`、`CONFIGURATION.md`、`SETUP.md`。其中 `CONFIGURATION.md` / `SETUP.md` 仍含 DeerFlow 措辞，按字段名/命令名为准。

## 11. 项目状态快照

按根目录 [`/CLAUDE.md` §7](../CLAUDE.md#7-项目状态快照强制) 强制维护 `<repo-root>/.claude/memory/project.md`。**回复结尾必须**有 `[snapshot:done]` 或 `[snapshot:noop]` 哨兵之一。
