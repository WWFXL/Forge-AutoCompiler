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
6. **强制验证**：识别 ELF/`ar` 结构，并对 executable 做 smoke test（`-version` / `--version` / `--help` 任一过即可）
7. **生成候选复现脚本**：提交验证先写出 `repro/build.sh`；脚本检出记录的完整 commit SHA，并按原 workdir 回放成功的 `run_container_bash` 命令
8. **自动 clean replay**：用原编译容器记录的不可变 `image_id` 启动新容器，在独立空目录中执行候选脚本，并比较产物集合、类型、大小、SHA-256 与 smoke 结果；只有全部通过才标记为 `verified`

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

### Windows + WSL2

Windows 用户请在 WSL2 Ubuntu 中运行项目。推荐使用 Docker Desktop 的 WSL Integration；也支持有意安装在 WSL 内的 Docker Engine，但所有构建和启动命令必须始终使用同一个 daemon。不要从 PowerShell 直接运行 Linux `.sh` 启动链。

```powershell
wsl -d Ubuntu
```

进入 WSL 后，在仓库根执行：

```bash
./scripts/wsl-check.sh
make config             # 仅首次
# 编辑 config.yaml 和所需模型环境变量
make compile-image      # 首次构建 C/C++ 编译环境
make docker-start
```

访问 <http://localhost:8000>。完整安装和故障排查见 [Install.md](Install.md#windows--wsl2推荐路径)。

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

# 4. 构建默认编译镜像（或在任务中指定你自己的镜像）
make compile-image

# 5. 装依赖
make install

# 6. 启动
make dev      # 本机模式，访问 http://localhost:8000
# 或
make docker-start   # Docker 开发模式
```

### 第一次跑

打开 http://localhost:8000 ，在欢迎页随便点一张 Action Card（已预填示例任务）：

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
nginx :8000 ── 统一反代入口
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
           submit_build_result()             ← 验证原产物、生成候选脚本并自动 clean replay；全部通过才置为 verified
       ↓
Lead:  finalize_session()  ← 停并删除容器；验证通过且有产物时状态置为 completed
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
repro/build.sh            # submit 生成的 commit-pinned 候选 bundle
replay/<attempt_id>/       # 每次自动 clean replay 的独立证据目录
├── recipe/build.sh       # 本次实际执行的候选脚本副本
├── workspace/            # 空白源码工作区，不复用原 session workspace
├── artifacts/            # replay 产生的产物，不覆盖原始 artifacts
└── logs/                 # replay 执行日志
```

**复现脚本和 clean replay 证据是这套系统的核心交付物**。`repro/build.sh` 从 `repo_url` 检出 session 记录的完整 `commit_sha`，只按原顺序和 workdir 回放成功的 `run_container_bash` 命令；失败尝试、clone/inspect 和 submit 审计事件不会进入脚本。脚本生成只是候选配方，不单独证明构建可从空环境复现。

`submit_build_result` 会把两层结果分开记录：`repro_bundle` check 只表示候选脚本安全且非空；随后系统自动创建唯一的 `replay/<attempt_id>/`，使用原编译容器解析出的完整 `image_id` 和空白挂载执行脚本。自动 replay 的执行/验证 deadline 由 `COMPILE_REPLAY_TIMEOUT_SECONDS` 控制，默认 `1200` 秒，覆盖网络与镜像检查、容器创建、脚本执行、产物遍历/分类/哈希和 smoke。系统以结构化 check 比较原始与 replay 产物的相对路径集合、ELF/`ar` 类型、字节大小、SHA-256，以及 executable 的 smoke 命令、退出码、有限预览和完整输出 SHA-256。任一执行、比较或清理步骤失败，session 都不会进入 `verified`。

Replay 容器不需要 Forge 后端或模型密钥，也不会挂载原 session 的 workspace/artifacts。容器创建握手在 session lifecycle lock 内完成并使用短时限；正常返回走 `finally` 清理，父任务取消会在 worker 停止前后各重新加载一次并按名称/ID 幂等清理。清理由独立的 `COMPILE_DOCKER_CLEANUP_TIMEOUT_SECONDS` 控制，默认 `20` 秒，stop 卡住时仍会尝试 bounded `rm -f`。原编译容器删除后、session 进入 `completed` 前，系统还会重新核对最终 `/artifacts` 的路径集合、类型、大小和 SHA-256，拒绝 replay 通过后的后台改写。`image_id` 只保证同一 Docker daemon 上的精确镜像身份：镜像被清理、换 daemon、换架构或外部依赖变化后，不承诺跨主机复现。

### 在 WSL2 中手动诊断 replay

自动验证失败时，可以用下面的命令诊断。它不会替代或改写 `session.json` 中的自动 replay 结果。必须进入运行 Forge 的同一个 WSL 发行版，并连接同一个 Docker daemon；不要在 PowerShell 的另一套 Docker context 中执行。`build.sh` 会清空挂载的 `/workspace` 和 `/artifacts`，因此只能使用新建的专用临时目录：

```bash
set -euo pipefail
SESSION_DIR="$PWD/.compile-sessions/<thread_id>/<session_id>"
REPLAY_RUN="$(mktemp -d)"
REPLAY_NAME="forge-manual-replay-$$"
REPLAY_TIMEOUT="${COMPILE_REPLAY_TIMEOUT_SECONDS:-1200}"
NETWORK="${COMPILE_RUNTIME_NETWORK:-compile_network_wwf_v1}"
IMAGE_ID="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["image_id"])' "$SESSION_DIR/session.json")"

cleanup() {
  docker rm -f "$REPLAY_NAME" >/dev/null 2>&1 || true
  rm -rf "$REPLAY_RUN"
}
trap cleanup EXIT INT TERM

mkdir -p "$REPLAY_RUN/workspace" "$REPLAY_RUN/artifacts"
docker image inspect "$IMAGE_ID" >/dev/null
docker run --rm --name "$REPLAY_NAME" \
  --network "$NETWORK" \
  --mount "type=bind,src=$(realpath "$SESSION_DIR/repro"),dst=/repro,readonly" \
  --mount "type=bind,src=$(realpath "$REPLAY_RUN/workspace"),dst=/workspace" \
  --mount "type=bind,src=$(realpath "$REPLAY_RUN/artifacts"),dst=/artifacts" \
  "$IMAGE_ID" timeout --signal=TERM --kill-after=5s "${REPLAY_TIMEOUT}s" bash /repro/build.sh

file "$REPLAY_RUN"/artifacts/*
sha256sum "$REPLAY_RUN"/artifacts/*
```

`--rm` 与 shell trap 共同覆盖正常退出和手动中断；自动验证还会在父任务取消时独立清理。若记录的 `image_id` 在当前 daemon 中不存在，应恢复原镜像，而不是退回同名可变 tag。

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
- C/C++ 编译会话使用独立的 `autocompiler:gcc13` 镜像；首次运行前执行 `make compile-image`。
- 自动 clean replay 的执行/验证时限由 `COMPILE_REPLAY_TIMEOUT_SECONDS` 设置，默认 `1200` 秒；清理另有默认 `20` 秒的 bounded budget。实际时限、duration 和镜像身份会写入 replay 证据。
- 宿主机必须设 `HOST_PROJECT_ROOT` 环境变量（本机模式由启动脚本注入；自己手动跑后端时要自己 export）。

---

## 协议

MIT License。详见 [LICENSE](./LICENSE)。

Forge-AutoCompiler 基于 DeerFlow 2.0 改造，致谢上游。
