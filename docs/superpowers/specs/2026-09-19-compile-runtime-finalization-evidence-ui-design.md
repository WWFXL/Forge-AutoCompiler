# 编译终态、资源、重放证据与子任务布局设计

日期：2026-09-19。状态：**Issue #271 已创建，实现与本地验证完成，待 PR/CI**。

本设计承接 Compile Runtime v2，只处理 2026-09-19 FMT 产品运行暴露的 P0、P1、P2 和前端展示问题。实施顺序固定为：Spec、Plan、GitHub Issue、失败测试、业务代码、完整验证、PR、CI、合并和知识库更新。

## 1. 真实证据

FMT 运行身份：

```text
thread_id  = 1b548923-7464-4128-80b5-0d90d6b77826
run_id     = 01a0b89b-acae-79f0-9f18-cd6a0bc829fb
session_id = c886b80e8fea
commit     = fd0a9b6620c8f44fac2122adb1cc29664aa96325
```

运行本身完成了 clone、CMake configure/build、22/22 CTest、候选验证、clean replay、finalize 和容器删除；session 为 `completed`，replay 为 `passed`。但是 LangGraph run 最终为 `error`，错误是：

```text
'Runtime' object has no attribute 'config'
```

服务器当前 LangGraph `Runtime` 只公开 `context`、`store`、`stream_writer` 和 `previous`。`run_id` 位于当前 `RunnableConfig`，必须通过框架支持的 `langgraph.config.get_config()` 读取，不能从 `runtime.config` 读取。

同一次运行还暴露了：

- 模型执行 `cmake --build ... -j 64` 和 `ctest ... -j 32`，共享服务器没有硬性 CPU 并行上限；
- 16 个公共头文件已复制到 `/artifacts`，却被 verifier 作为“非编译文件”忽略；
- 初始构建运行了 CTest，clean replay 只重建产物，没有再次运行测试；
- compile/replay 的 `docker stop` 都与 Docker 默认 10 秒宽限期发生外层超时竞态，随后 `docker rm -f` 才删除容器；
- `selected_build_system=cmake`，但产品 session 的 `executed_build_system=null`；
- DeepSeek 返回 `additional_kwargs.reasoning_content=""`。前端把“字段存在”误判为“有 reasoning”，渲染出一个只有 6px 高度的空 `MessageGroup` 边框，形成横线并挤压“执行 1 个子任务”标题。

## 2. 目标

### P0：成功终态可靠

1. Middleware 使用真实 LangGraph Runtime 契约读取 thread/run identity。
2. 已成功 finalize 的 session 不再因为 after-agent 清理 hook 的接口错误把 run 标为失败。
3. 未完成 session 仍由 after-agent 执行 run-owned cleanup；不能为了保护成功结果而吞掉真实清理失败。
4. 测试使用真实 `Runtime` 和 runnable context，不再用伪造 `.config` 的对象掩盖接口漂移。

### P1：共享服务器资源有界

1. 每个 compile/replay 容器使用同一份持久化并行策略。
2. 默认并行上限为 4，可由正整数环境变量显式覆盖。
3. Docker `--cpus` 是硬性 CPU quota；即使命令显式写 `-j 64`，容器也不能获得超过策略值的 CPU 时间。
4. 同时注入 `CMAKE_BUILD_PARALLEL_LEVEL`、`CTEST_PARALLEL_LEVEL` 和 `MAKEFLAGS`，让未显式指定并行度的常见构建工具遵循上限。
5. Compiler 提示词要求不自行拼接 `-j$(nproc)`、裸 `-j` 或高于策略的并行参数，但提示词不是唯一防线。
6. 策略写入 `session.json` 和 lifecycle 事件；clean replay 复用 session 冻结值，不读取可能已经变化的进程环境。

### P2：交付与 replay 证据完整

1. `/artifacts` 中的编译产物继续执行 ELF/`ar` 分类和 executable smoke。
2. 普通非符号链接文件作为 `support_file` 纳入 manifest，记录相对路径、字节大小和 SHA-256；允许头文件、CMake package 文件和许可证等配套交付物。
3. 至少仍需一个真正的 compiled artifact，只有文本文件不能让提交通过。
4. replay 比较完整 manifest，包括 compiled artifacts 和 support files；support file 不做 ELF 或 executable smoke 判定。
5. finalize 后再次核对同一完整 manifest，阻止 replay 通过后配套文件被修改、增加或删除。
6. `submit_build_result` 除 build recipe IDs 外，接收独立的 `verification_command_ids`：只允许当前 session 中成功、未超时、role 为 `smoke` 的命令。
7. 系统分别生成 `repro/build.sh` 与可选的 `repro/verify.sh`。clean replay 在同一干净容器内先运行 build script，再运行 verification script；二者有独立日志、退出码和 check。
8. 当 supporting build 后存在成功 smoke 命令时，提交必须显式选入至少一个 verification command；没有可用项目测试的任务可提交空列表。
9. 产品与实验路径都从 supporting build 及其前序 configure 证据推导 `executed_build_system`，在 submit 前持久化并记录事件。
10. Docker stop 显式传入短于外层 cleanup budget 的 grace period，subprocess timeout 额外保留控制面缓冲；stop 失败仍继续有界 `rm -f`。

### 前端布局

1. `hasReasoning` 只在实际 reasoning 文本去除空白后非空时返回 true。
2. 空 `reasoning_content` 不创建空 `MessageGroup`，子任务标题前不再出现孤立横线。
3. 固定真实消息 fixture，覆盖“查看其他步骤”、空 reasoning 的 task、Compiler 卡、finalize 工具组和最终 Markdown。
4. 桌面、手机和短屏断言标题、卡片、前一消息组边界不重叠、无横向溢出、无 console error。

## 3. Runtime identity 修复

`CompileTerminationMiddleware._run_identity()` 的读取顺序：

1. 从 `runtime.context` 读取 `thread_id` / `run_id`；
2. 缺失字段时调用 `get_config()`；
3. 从 `configurable.thread_id`、`configurable.run_id` 和顶层 `run_id` 回退；
4. 若 hook 在 runnable context 外被直接调用，捕获 `get_config()` 的“无 context”错误并按缺少身份 no-op；
5. 不访问不存在的 `runtime.config`，不从全局变量猜测 run。

清理函数的异常语义保持不变：身份缺失时不清理；身份存在且清理失败时错误继续上抛。这样既不让 no-op hook 覆盖成功终态，也不隐藏实际资源泄漏。

## 4. 资源策略

新增 session 字段：

```text
parallel_jobs: int
```

默认来源：

```text
COMPILE_MAX_PARALLEL_JOBS=4
```

prepare 创建 session 时解析并冻结该值。compile 与 replay `docker run` 都加入：

```text
--cpus <parallel_jobs>
--env CMAKE_BUILD_PARALLEL_LEVEL=<parallel_jobs>
--env CTEST_PARALLEL_LEVEL=<parallel_jobs>
--env MAKEFLAGS=-j<parallel_jobs>
```

这不是精确的内存配额方案，也不试图解析任意 shell 中所有构建器参数；它提供容器级 CPU 硬边界和主流工具默认值。内存、PID、磁盘或全局多任务调度属于后续独立容量设计。

## 5. 完整 artifact manifest

`BuildArtifact.artifact_type` 扩展为：

```text
executable | shared_library | object | static_library | support_file
```

候选遍历规则：

- 只接收 `/artifacts` 下的普通文件；符号链接和逃逸路径拒绝或忽略并留下 note；
- compiled artifact 必须非空，并执行既有类型/smoke 规则；
- support file 记录 size/SHA，不要求可执行或 ELF，不因内容为空自动失败；
- 提交通过条件仍要求至少一个 compiled artifact；
- 文件集合用相对 POSIX 路径排序，目录本身不作为 artifact，目录结构由文件路径隐式表达。

replay 与 finalize 使用同一个分类函数和 manifest 比较器，避免候选、重放、终结三处语义漂移。

## 6. Build recipe 与 verification recipe

提交接口：

```json
{
  "supporting_command_id": "command_build",
  "recipe_command_ids": [
    "command_configure",
    "command_build",
    "command_artifact_stage"
  ],
  "verification_command_ids": [
    "command_ctest"
  ]
}
```

`ReplayRecipe` 分别持久化 `steps` 与 `verification_steps`，fingerprint 同时覆盖两组步骤、commit、image、资源策略和 artifact manifest。

Build recipe 保持现有允许角色和最小性规则。Verification recipe 额外要求：

- command ID 唯一、属于当前 session、执行成功且未超时；
- role 必须是 `smoke`；
- 保持原始审计顺序；
- workdir 和命令满足现有可移植性检查；
- verification command 必须位于 supporting build 之后；
- 不允许 diagnostic、任意日志查看或 host/session 路径进入验证脚本。

replay 执行顺序固定为 clone 固定 commit、`build.sh`、可选 `verify.sh`、artifact manifest 比较。Build 和 verification 各自失败时使用不同稳定 classification，避免把 CTest 失败误报为产物哈希失败。

## 7. Docker cleanup 时限

新增：

```text
COMPILE_DOCKER_STOP_GRACE_SECONDS=3
```

约束：

- grace 至少 1 秒，且必须给 cleanup budget 中的 `rm -f` 留出缓冲；
- `docker stop --time <grace>` 的 subprocess timeout 为 grace 加固定控制面缓冲，并受总 cleanup deadline 限制；
- stop 超时或失败仍执行 `docker rm -f`；
- `ContainerCleanupResult` 保留 stopped/removed 两个事实，overall success 仍以需要删除时实际 removed 为准；
- 事件同时记录 Docker grace 和 subprocess timeout，便于区分容器未响应与 CLI 控制面超时。

## 8. 构建系统证据

`_infer_executed_build_system()` 不再只服务 active experiment。每次 submit 均：

1. 从 supporting build 和之前成功 configure 命令推导实际系统；
2. 持久化 `executed_build_system`；
3. 记录产品 workflow event；
4. active experiment 在此结果上追加冻结策略匹配检查，而不维护第二套推导逻辑。

无法证明时允许字段为 null，但事件必须说明 unproven；产品展示不能把 `selected_build_system` 冒充为实际执行证据。

## 9. 测试策略

### 后端无模型测试

- 真实 `Runtime` + runnable context 读取 identity；不存在 `.config` 也不报错。
- middleware async lifecycle：completed session 不被覆盖，unfinished session 调用 cleanup，cleanup 异常不被吞掉。
- compile/replay Docker 命令包含同一 frozen CPU policy 和环境变量。
- session round-trip 保留 `parallel_jobs`、support files、verification recipe 和 verification replay evidence。
- headers/support files 候选、replay、finalize 三段路径/size/SHA 一致；只有 support files 时拒绝。
- CTest verification script 成功/失败、非法 role、乱序、跨 session、不可移植路径和 fingerprint 去重。
- stop 命令包含显式 `--time`，外层 timeout 大于 grace，并为 `rm -f` 留出预算。
- 产品 submit 持久化 `executed_build_system`，active experiment 继续使用同一结果。

### 前端

- Node 单测：空白 reasoning 为 false，非空 reasoning 为 true。
- Playwright 离线 fixture：空 reasoning task 前没有空卡片，子任务标题与 Compiler 卡边界有正间距。
- 1280x900、390x844、1280x500 均无覆盖、横向溢出或 console error。

### 全量门禁

- backend 定向测试、相邻 compile/middleware/Gateway 测试、当前产品全量 pytest、Ruff check/format；
- frontend Node tests、ESLint、TypeScript、Prettier、production build、Playwright；
- frozen benchmark tests 在 predecessor revision 运行；
- 不调用真实 provider，不创建正式 experiment evidence。

## 10. Runtime 身份与兼容边界

`forge-compile-runtime-v2` 的 component hashes 已固定，必须保留为历史只读身份。本次会改变 middleware、Docker runtime、session schema、submit 工具和 replay 语义，因此发布新的 `forge-compile-runtime-v3` 工程身份：

- predecessor 为 `main@9ddf428e`；
- `interactive_product_validation=true`；
- `provider_experiment_execution=false`；
- `formal_collection=false`。

现有 session loader 可为缺失的新持久化字段提供数据默认值，以便历史页面读取；不保留旧的内部提交工具 schema，也不把旧 run 重新解释为 v3 evidence。历史 benchmark、manifest、evidence 和 Runtime v2 文件不修改。

## 11. 非目标

- 不调用 provider canary，不启动正式实验。
- 不清理用户要求保留的旧 gRPC 容器。
- 不升级 LangGraph API 版本，不顺手处理 EOL 警告。
- 不解决持久化 checkpointer 的跨服务重建问题。
- 不加入可接受非零退出码。
- 不实现复杂仓库的子模块、依赖缓存、文档优先级和阶段预算规则。
- 不显示或伪造模型私有思考，只修复空 reasoning 产生的布局元素。
- 不实现内存/PID/磁盘配额或跨用户全局调度器。

## 12. 验收标准

- FMT 等成功任务在 finalize 后 run 为成功，不出现 `Runtime.config` 错误。
- 同一 session 的 compile/replay 都显示并执行相同 `parallel_jobs`，Docker CPU quota 可审计。
- FMT 两个静态库和公共头文件全部进入 manifest，clean replay 后路径/size/SHA 一致。
- 初始 CTest 成功时，clean replay 也实际执行选定测试并单独记录结果。
- `executed_build_system=cmake` 在产品 session 中持久化。
- 正常 compile/replay cleanup 不再因 Docker 默认 10 秒 grace 与外层 timeout 同值而稳定等待到超时。
- DeepSeek 空 reasoning 不渲染孤立横线；截图中的标题和卡片不重叠。
- 新 Runtime 身份仍只允许交互式工程验证；历史 v2 和正式实验资产无 diff。
