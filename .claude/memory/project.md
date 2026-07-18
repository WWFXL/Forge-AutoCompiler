# 项目状态快照 (Project State Snapshot)

跨 Claude Code session 的项目状态流水。按 CLAUDE.md §7 维护。

## 进行中 (In Progress)
<!-- 跨 session 未完成的工作。完成后挪到「最近变更」。 -->

## 最近变更 (Recent Changes)
<!-- 倒序，最新在上。 -->

- 2026-07-20 — 将 physical-attempt evidence ledger 重排到最新主干并修复模型工厂测试契约
  - 文件: `backend/tests/test_lead_agent_model_resolution.py`, `.claude/memory/project.md`
  - 动机: PR #13 在 `main` 已包含 Issue #10 后改为单提交增量；模型工厂新增实验 thread/role 参数后，同步测试替身并断言普通会话不会携带实验 thread ID
  - 证据: benchmark/ledger/runner `87 passed`，compile runtime/terminal/cancellation `114 passed`，模型 middleware/factory `30 passed`，后端全量 `1489 passed, 17 skipped`，真实 Docker replay `2 passed in 75.55s`；Ruff、Compose、前端 lint/typecheck/build、冻结资产、diff 与敏感信息检查通过

- 2026-07-20 — 将 C/C++ benchmark 协议重排到最新主干并完成发布前验证
  - 文件: `scripts/forge_benchmark.py`, `backend/tests/test_forge_benchmark.py`, `benchmarks/README.md`, `benchmarks/manifests/cpp-pilot-v1.json`, `benchmarks/schemas/forge-cpp-benchmark-v1.schema.json`, `.github/workflows/backend-unit-tests.yml`
  - 动机: 在不改写 v1-v5 冻结 manifest、Schema、记录器或账本的前提下，把 Issue #10 的协议增量从旧 clean-replay 分支重放到 `main`；Forge 组件按 manifest 声明的历史 Git revision 校验，当前 recorder 与 Schema 仍按工作树字节校验，CI checkout 获取完整历史以执行同一严格检查
  - 证据: 聚焦回归 `183 passed`，后端全量 `1470 passed, 17 skipped`，后端 Ruff、前端 lint/typecheck/build、Draft 2020-12 meta-schema、冻结资产、diff 与敏感信息检查通过

- 2026-07-18 — 实现 C/C++ pilot runner 与 physical-attempt evidence ledger
  - 文件: `scripts/forge_benchmark_runner.py`, `backend/packages/harness/deerflow/compile/evidence.py`, `backend/packages/harness/deerflow/compile/operations.py`, `backend/packages/harness/deerflow/agents/middlewares/llm_error_handling_middleware.py`, `backend/tests/test_experiment_evidence.py`, `backend/tests/test_forge_benchmark_runner.py`
  - 动机: 在首个模型请求前持久化实验尝试，以 hash chain 记录物理模型请求、命令、submit/replay/delivery gate、actual model/endpoint 和 orphan reconciliation；runner 强制 exact commit、镜像、依赖、环境、有序构建参数、replay delay、模型重试/超时与 compiler 预算，且拒绝重复 slot、fallback、密钥/宿主路径和终态后写入
  - 证据: benchmark/ledger/runner `87 passed`，compile runtime/terminal/cancellation `114 passed`，模型 middleware/factory `30 passed`，真实 Docker replay `2 passed in 63.14s`；定向 Ruff/format、`py_compile`、Compose config、`git diff --check` 与 WSL preflight 通过

- 2026-07-18 — 冻结 C/C++ pilot 协议、manifest、证据 Schema 与原子 JSONL 记录器
  - 文件: `scripts/forge_benchmark.py`, `backend/tests/test_forge_benchmark.py`, `benchmarks/README.md`, `benchmarks/manifests/cpp-pilot-v1.json`, `benchmarks/schemas/forge-cpp-benchmark-v1.schema.json`
  - 动机: 用 5 个 exact-commit C/C++ case 固定模型、端点、WSL/Docker、镜像、超时/重试与 lifecycle 口径，并让每条 run record 可校验、可锁定、可重复拒绝且不含密钥或宿主路径；本阶段只完成采集基础设施，未发起模型 pilot
  - 证据: benchmark `75 passed`，compile runtime/terminal/cancellation `108 passed`，Ruff check/format、`py_compile`、Draft 2020-12 meta-schema、Windows/WSL manifest digest 对照及独立 P1/P2 复核通过

- 2026-07-17 — 自动在独立容器中验证候选构建 recipe，并把 replay 证据纳入完成条件
  - 文件: `backend/packages/harness/deerflow/compile/docker_runtime.py`, `backend/packages/harness/deerflow/compile/manager.py`, `backend/packages/harness/deerflow/compile/operations.py`, `backend/packages/harness/deerflow/compile/schemas.py`, `backend/tests/test_compile_runtime.py`, `backend/tests/test_compile_cancellation.py`, `backend/tests/test_compile_replay_docker.py`
  - 动机: 使用不可变镜像 ID、空 workspace/artifacts 和只读 recipe 执行 clean replay，严格比较产物集合、类型、大小、SHA-256 与 smoke 输出；用 session termination fence、持锁 container checkpoint、超时后按名称对账和终态白名单合并处理取消/超时竞态
  - 证据: compile runtime/terminal/cancellation 共 `108 passed`，真实 Docker integration `2 passed`，Ruff check/format 与独立 P1/P2 复核通过
  - GitHub: PR #9 已 squash 合并为 `a4ffdbde`，Issue #7 已关闭

- 2026-07-17 — 生成固定源码且可在全新 C/C++ 编译容器中回放的候选构建脚本
  - 文件: `backend/packages/harness/deerflow/compile/operations.py`, `backend/tests/test_compile_runtime.py`, `README_zh.md`, `CONTRIBUTING.md`, `CLAUDE.md`, `backend/CLAUDE.md`
  - 动机: 从审计轨迹中筛选成功 bash 步骤，固定实际 clone URL 与完整 commit SHA，隔离宿主路径并把 replay 生成失败纳入验证；两次独立 `autocompiler:gcc13` replay 均得到相同 16,504 字节 ELF 和基线 SHA-256

- 2026-07-15 — 支持在 Windows + WSL2 中运行 Docker 开发环境和嵌套编译容器
  - 文件: `scripts/wsl-check.sh`, `scripts/docker.sh`, `docker/docker-compose-dev.yaml`, `docker/compile/Dockerfile`, `backend/packages/harness/deerflow/config/paths.py`, `backend/packages/harness/deerflow/compile/docker_runtime.py`
  - 动机: 统一服务可见路径与宿主 Docker 可见路径，补齐编译镜像、网络、配置模板和可复现的 WSL 启动流程

## 待办 (TODOs)
<!-- 发现但未做的事。带 file:line 指针。 -->

- 完成 Issue #11 / PR #13 的审阅、完整 CI 与主干合并；处理堆叠链期间不启动 v6 pilot，也不删除仍被上层 PR 引用的 base 分支。
- Issue #11 交付后创建新版 manifest，重新冻结包含 evidence middleware、runner、prompt constraint injection 与新工具契约的 Forge revision/component hashes，并解除 `instrumentation_blocker`；v1 manifest 保持不可变。
- 新版 manifest preflight 全绿后，按 `gpt-5.6-sol` 串行执行五个 case 的首次 pilot；任何 DeepSeek 或其他模型对照必须使用单独版本化 condition/manifest，不能混入冻结 baseline。
- 当前 `backend/packages/harness/deerflow/compile/manager.py` 的 lifecycle lock 是进程内锁；部署多个后端进程前，需要改为文件锁/数据库事务或带版本号的 CAS，并增加跨进程竞态测试。

## 已知问题 (Known Issues / Pitfalls)
<!-- 工作中踩过的坑、限制或意外行为。 -->

- 协作语言约定：后续 GitHub Issue、Pull Request、评论、评审说明和提交说明默认使用中文；分支名、代码标识、命令和必要技术术语继续遵循仓库的 ASCII/既有命名规范。若外部协作明确要求英文，先向用户确认。
- Docker Desktop 与 WSL 原生 Docker Engine 是两个独立 daemon，镜像、网络和容器不共享；Forge 命令必须始终在同一套 daemon 上执行。
- WSL 的 `127.0.0.1` 代理不能直接传入 Docker build；编译镜像代理必须使用容器可达地址。
- 后端全量 Ruff 当前有 9 个本次改动之外的既有错误；相关改动文件的定向 Ruff 已通过。
- 成功 bash 记录只是候选 recipe；失败命令可能留下持久副作用。进入研究基线前必须在新容器与空 `/workspace`、`/artifacts` 中实际 replay，不能把 `repro_bundle` 生成成功等同于独立复现成功。
- Windows 挂载目录在编译镜像中可能触发 Git `dubious ownership`；replay 初始化仓库后必须把 `/workspace/repo` 加入 `safe.directory`。
- 不要把含 `$()`、重定向和多层引号的后验校验直接嵌进 PowerShell → WSL → `docker run ... bash -lc`；参数可能被中间层重解释。应先单独运行 `bash /repro/build.sh` 获取退出码，再用独立命令检查类型、输出与哈希。
- `docker run` 客户端超时不证明 daemon 没有稍后创建容器；replay 必须使用确定性名称，在超时后反复对账并幂等删除，且 create/checkpoint/parent cleanup 必须由同一 session lock 串行化。
- 取消、超时与同步 submit 可能持有不同的 stale session 副本；第一条持久化 termination reason 必须胜出，终态后的 cleanup 只能按 `attempt_id` 白名单合并可变清理字段，不能覆盖镜像、commit、recipe、产物或检查证据。
- Manifest 中声明的模型、端点、镜像和运行参数只是实验意图，不是实际运行证明；observed 字段必须由 runner 从真实请求、Forge 状态和 Docker 结果写入。
- Benchmark run record 必须固定 recorder 与 Schema 的 SHA-256；只固定 manifest 不足以证明不同批次使用了相同采集语义。
- 没有观测到的实际模型、镜像 ID、submit/replay 结果等字段必须保持 `null`，不能用 manifest 声明值、预期结果或事后推断补齐证据。
- 历史 manifest 的 Forge 组件哈希必须按其声明的 Git revision 读取 blob 校验；把它永久对照最新工作树，会在 stacked PR squash 合并或后续 instrumentation 后产生伪漂移。协议记录器与 Schema 仍应按当前字节校验；最小后端镜像没有 Git 时，由运行时 preflight 校验当前工作树。
- 一次性前端测试容器的镜像内置源码可能落后于主干；应只读挂载当前 `frontend/src`、`public` 和 `next.config.js`，并让容器使用独立 `.next`，不能在运行 `next dev` 的容器内并发构建。
- Actions checkout 默认 `fetch-depth: 1`；需要读取 manifest 固定历史 revision 的 benchmark 测试必须显式获取完整 Git 历史，否则本地完整 clone 通过而 CI 会因找不到历史路径失败。
- Compose 中只读挂载的 `/repo` 适合 runner/preflight，但 Ruff/pytest 必须关闭仓库内缓存；需要格式化时使用一次性可写 bind mount。WSL 宿主当前没有 `uv`，标准库 runner 可直接运行，依赖完整的回归测试继续在 LangGraph 开发容器中执行。
- Manifest 的 CMake/configure 参数必须确定性注入 compiler prompt，并按有序 token 子序列验证；只检查参数集合会掩盖顺序敏感的配置偏差。
- 在仓库根直接启动 Compose 会改变 project name，并可能因网络网段重叠创建失败；开发服务必须继续使用既定 `deer-flow-dev` project/启动脚本。
- Compose 开发容器只把完整仓库只读挂载到 `/repo`，而 `/app/backend` 仅是后端源码挂载；依赖仓库根资产的 pytest/Ruff 必须从 `/repo/backend` 运行，并使用 `/app/backend/.venv` 解释器、关闭仓库内缓存。
