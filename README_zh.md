# Forge-AutoCompiler

**Forge-AutoCompiler** 是一个面向 C/C++ 仓库的自动化编译系统。给一个 Git 仓库 URL，系统会在隔离的 Docker 容器中拉代码、识别构建系统、由 AI 子代理迭代构建、自动验证产物，并生成可复现的构建脚本。

> 项目从 [DeerFlow 2.0](https://github.com/bytedance/deer-flow) fork 而来，核心已聚焦到「自动化编译」。Python 包名 `deerflow.*` 作为内部实现细节保留。

---

## 这是什么

一个把 **「克隆 → 识别 → 编译 → 验证 → 复现」** 全流程自动化的系统。你只需要：

```
克隆并编译 https://github.com/fmtlib/fmt
```

系统会自己完成：

1. **创建编译会话**：在 Docker 容器（默认 `autocompiler:gcc13`）中开辟独立工作区
2. **克隆仓库**：浅克隆到容器内 `/workspace/repo`
3. **识别构建系统**：按 `CMakeLists.txt` / `Makefile` / `configure` 顺序探测
4. **委派 compiler 子代理**：子代理在容器内反复 `configure` / `build`，遇到依赖错误自动 `apt install`、清缓存重试
5. **拷贝产物到 `/artifacts`**：只拷最终可执行物/库，不整目录倾倒
6. **强制验证**：逐文件检查 exists / non-empty / smoke test（`--version` / `-version` / `--help` 任一过即可）
7. **生成复现脚本**：验证通过后自动写出 `repro/build.sh`，回放整套命令

整个过程通过 Web 工作台（基于 Next.js）或后端 SDK 调用。

## 适用范围

✅ **目前支持**：
- 构建系统：**CMake**、**Make**、**Autotools**
- 语言：**C / C++**
- 仓库类型：标准 Linux 项目（含 git submodule）

❌ **暂未覆盖**（与编译核心无关，未来可能加）：
- Rust（Cargo）/ Go / Node / Java / Python
- Bazel / Meson 等其他构建系统
- Windows / macOS 原生构建

---

## 快速开始

### 前置

- Node.js 22+
- pnpm 10.26.2+
- Python 3.12+
- [uv](https://docs.astral.sh/uv/)（Python 包管理）
- nginx（本机模式用于反代）
- Docker（编译容器运行时）

### 配置

```bash
# 1. 克隆并进入仓库
git clone <repo>
cd Forge-AutoCompiler

# 2. 生成本地配置（首次）
make config

# 3. 编辑 config.yaml：至少配置一个 LLM 模型
#    config.yaml 中以 $ 开头的值会从环境变量取
export OPENAI_API_KEY="..."   # 或你用的模型对应的 key

# 4. 编辑 config.yaml 中的 sandbox 段并确保宿主机上有编译镜像
docker pull autocompiler:gcc13   # 或在 config.yaml 中改成你自己的镜像

# 5. 装依赖
make install

# 6. 启动
make dev      # 本机模式，访问 http://localhost:2026
# 或
make docker-start   # Docker 开发模式
```

### 第一次跑

打开 http://localhost:2026 ，在欢迎页随便点一张 Action Card（已预填示例任务）：

- "克隆并编译 https://github.com/fmtlib/fmt"（CMake 项目）
- "克隆并深度解析编译 https://github.com/grpc/grpc"（含 submodule 的复杂项目）

或者直接对 agent 说自然语言：

```
帮我编译 <repo_url>，分支是 master
```

### 关停

```bash
make stop      # 停所有本机服务
make clean     # stop 并清理本地缓存（.deer-flow/、logs/）
```

---

## 架构

```
浏览器
  ↓
nginx :2026 ── 统一反代入口
  ├→ frontend (Next.js) :3000      非 API 请求
  ├→ gateway (FastAPI)   :8001     /api/*（models / skills / memory / uploads / threads / artifacts）
  └→ langgraph server    :2024     /api/langgraph/*（agent 运行时）
```

**核心代码组织**：

```
backend/packages/harness/deerflow/
├── agents/lead_agent/        # Lead Agent（决策编译流程）
├── subagents/builtins/
│   └── compiler_agent.py     # ★ compiler 子代理（执行构建与提交产物）
├── compile/                  # ★ 编译核心
│   ├── schemas.py            # CompileSession / BuildCommandRecord / ...
│   ├── manager.py            # 会话管理 + JSONL 事件日志
│   ├── operations.py         # prepare/clone/inspect/submit/finalize
│   ├── docker_runtime.py     # 容器生命周期
│   └── paths.py              # 路径命名
└── tools/
    ├── builtins/agent_compile_tools.py   # Lead 用的工具
    └── bound_compile_tools.py            # compiler 子代理用的工具
```

**Lead Agent ↔ Compiler 子代理**：

```
Lead:  prepare_compile_session(repo_url)
       → clone_repository()
       → identify_build_system()
       → task(subagent_type="compiler", prompt=...)        ← 委派
       ↓
Compiler:  run_container_bash("cmake ...")  ← 反复迭代
           run_container_bash("make -j")
           ...                              ← 失败必改策略，禁止盲目重试
           run_container_bash("cp .../app /artifacts/")
           submit_build_result()             ← 触发验证
       ↓
Lead:  finalize_session()  ← 停容器、写复现脚本
```

更详细的：
- [`CLAUDE.md`](CLAUDE.md) — 给 AI 编程助手用的总指南
- [`backend/CLAUDE.md`](backend/CLAUDE.md) — 后端实现细节
- [`frontend/CLAUDE.md`](frontend/CLAUDE.md) — 前端实现细节
- [`docs/run_compile_workflow_workflow_mechanism.md`](docs/run_compile_workflow_workflow_mechanism.md) — 工作流机制说明
- [`docs/current_compile_project_implementation.md`](docs/current_compile_project_implementation.md) — 当前实现自审

---

## 会话产物在哪

每次编译会在宿主机 `$HOST_PROJECT_ROOT/.compile-sessions/{thread_id}/{session_id}/` 下生成：

```
session.json              # CompileSession 元数据
workspace/repo/           # 克隆的源码
artifacts/                # 子代理提交的最终产物
logs/
├── workflow.log          # JSONL 事件流（session.created、command.recorded、...）
├── 001_clone.log         # 每条命令的完整 stdout+stderr
└── ...
repro/build.sh            # 验证通过后生成的可执行构建脚本
```

**复现脚本是这套系统的核心交付物**——任何一次成功编译都能用 `repro/build.sh` 在同样的镜像里复现。

---

## DeerFlow 遗留

下列能力**仍在代码里**，但**与编译核心无关**，是 DeerFlow 2.0 时期遗留：

- IM 渠道桥接：Feishu / Slack / Telegram / WeCom（`backend/app/channels/`）
- 通用 skills：`skills/public/` 下 20+ 个（deep-research、image-generation、newsletter-generation 等）
- 长期 memory：`backend/packages/harness/deerflow/agents/memory/`
- MCP 集成：`backend/packages/harness/deerflow/mcp/`
- LangSmith / Langfuse tracing：可启用但非必需

未来可能裁剪。请**不要据此推断产品定位**——产品定位是「自动化编译」。

---

## 配置要点

- `config.yaml` 在项目根，从 `config.example.yaml` 复制。schema 升级跑 `make config-upgrade`。
- 至少需要一个可用的 LLM 模型条目（`models[]`）。
- 编译镜像在 `config.yaml` 的 `sandbox` 段（或在 `compile/manager.py` 的 `DEFAULT_COMPILE_IMAGE` 兜底）。
- 宿主机必须设 `HOST_PROJECT_ROOT` 环境变量（本机模式由启动脚本注入；自己手动跑后端时要自己 export）。

---

## 协议

MIT License。详见 [LICENSE](./LICENSE)。

Forge-AutoCompiler 基于 DeerFlow 2.0 改造，致谢上游。
