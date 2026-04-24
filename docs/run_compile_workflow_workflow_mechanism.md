# `run_compile_workflow` 工具内部工作流说明

本文档完整描述 `run_compile_workflow` 工具在 DeerFlow 中的内部工作机制，包括：

- 入口与整体调用关系
- 工作流状态流转
- 各阶段职责
- 各阶段输入/输出
- 中间状态与最终结果的区别
- 本次设计中需要特别注意的语义细节
- 当前已识别问题与改进建议

---

## 1. 工具入口与整体职责

`run_compile_workflow` 是 `lead_agent` 在收到“编译远程仓库”类请求后调用的高层工具。它本身不是单步编译命令，而是一个**多阶段编译工作流编排器**。

工具入口如下：

```11:34:/workspace/deer-flow/backend/packages/harness/deerflow/tools/builtins/compile_workflow_tool.py
@tool("run_compile_workflow", parse_docstring=True)
def run_compile_workflow(
    runtime: ToolRuntime[ContextT, ThreadState],
    repo_url: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    branch: str | None = None,
    task_description: str | None = None,
    artifact_hint: str | None = None,
    build_goal: str | None = None,
    max_build_attempts: int = 4,
    generate_repro_bundle: bool = True,
) -> str:
```

它的核心行为是：

1. 从当前 `runtime` 提取线程信息与子代理 owner 信息。
2. 组装 `CompileWorkflowInput`。
3. 调用 `CompileWorkflowRunner.run(...)` 执行完整工作流。
4. 将最终 `CompileWorkflowResult` 渲染为一段文本字符串返回给 `lead_agent`。

这意味着：

- `lead_agent` **看不到内部逐步状态机事件**。
- `lead_agent` **只拿到最终汇总结果**。

---

## 2. 总体架构分层

整体分为四层：

### 2.1 工具层
- 文件：`backend/packages/harness/deerflow/tools/builtins/compile_workflow_tool.py`
- 职责：接收 tool 参数，调用 workflow runner，格式化最终输出。

### 2.2 工作流编排层
- 文件：`backend/packages/harness/deerflow/compile/workflow/runner.py`
- 职责：按固定顺序执行 prepare → clone → inspect → build → verify → finalize。

### 2.3 阶段实现层
- 文件：`backend/packages/harness/deerflow/compile/workflow/stages.py`
- 职责：定义每个阶段如何修改 `CompileWorkflowState`，以及调用哪些底层操作。

### 2.4 底层编译操作层
- 文件：`backend/packages/harness/deerflow/compile/operations.py`
- 职责：真正创建编译 session、建容器、clone、探测构建系统、执行命令、记录产物、verify、finalize。

此外，构建阶段还会额外调用一个**编译子代理**：

- 文件：`backend/packages/harness/deerflow/compile/workflow/build_subagent_runner.py`
- 职责：把构建阶段交给 `compiler` subagent 执行，由其返回受约束的 JSON 结果。

---

## 3. 输入数据结构

工作流输入结构定义如下：

```8:18:/workspace/deer-flow/backend/packages/harness/deerflow/compile/workflow/schemas.py
@dataclass
class CompileWorkflowInput:
    repo_url: str
    thread_id: str
    branch: str | None = None
    task_description: str | None = None
    artifact_hint: str | None = None
    build_goal: str | None = None
    max_build_attempts: int = 4
    owner_id: str | None = None
    generate_repro_bundle: bool = True
```

字段含义：

- `repo_url`：目标 Git 仓库地址。
- `thread_id`：当前对话线程，用于 session 隔离。
- `branch`：可选分支。
- `task_description`：可选任务描述，会被写入 session summary 初值。
- `artifact_hint`：可选产物提示，用于 verify 阶段匹配目标产物。
- `build_goal`：构建目标描述，如 release binary。
- `max_build_attempts`：允许构建子代理尝试的最大次数。
- `owner_id`：归属的 agent / subagent 身份。
- `generate_repro_bundle`：是否生成 repro 脚本。

---

## 4. 中间状态数据结构

工作流内部通过 `CompileWorkflowState` 在各阶段之间传递上下文与结果：

```41:61:/workspace/deer-flow/backend/packages/harness/deerflow/compile/workflow/schemas.py
@dataclass
class CompileWorkflowState:
    thread_id: str
    repo_url: str
    branch: str | None = None
    task_description: str | None = None
    artifact_hint: str | None = None
    build_goal: str | None = None
    owner_id: str | None = None
    session_id: str | None = None
    build_system: str | None = None
    status: str = "pending"
    error: str | None = None
    summary: str | None = None
    final_error: str | None = None
    warnings: list[str] = field(default_factory=list)
    verify_message: str | None = None
    prepare_done: bool = False
    clone_done: bool = False
    inspect_done: bool = False
    build_done: bool = False
    verify_done: bool = False
    finalized: bool = False
```

可以把它理解成 workflow 的“单一事实来源”，里面包含：

- 流程进度标记：`prepare_done` / `clone_done` / `inspect_done` / `build_done` / `verify_done` / `finalized`
- 业务状态：`status`
- 编译上下文：`session_id` / `build_system`
- 结果数据：`summary` / `final_error` / `warnings` / `attempts` / `artifacts` / `logs` / `repro_files`

其中新增的两项语义尤其重要：

- `warnings`：用于承载“曾经出错但已经恢复”的信息，避免直接污染最终错误字段。
- `final_error`：仅用于表示最终未恢复、真正导致 workflow 失败的错误。

---

## 5. 最终结果数据结构

工作流最终返回的是 `CompileWorkflowResult`：

```64:75:/workspace/deer-flow/backend/packages/harness/deerflow/compile/workflow/schemas.py
@dataclass
class CompileWorkflowResult:
    status: str
    summary: str
    session_id: str | None
    build_system: str | None
    attempts: list[BuildAttempt]
    artifacts: list[str]
    logs: list[str]
    repro_files: list[str]
    verify_message: str | None = None
    warnings: list[str] = field(default_factory=list)
    final_error: str | None = None
```

注意：

- 这是**最终聚合结果**。
- 工具层会把这个结果再格式化成字符串。
- `lead_agent` 看到的是字符串，不是这个 dataclass 本身。

相比旧版返回结构，这一版把：

- `warnings`
- `final_error`

显式分开，减少了“历史错误”和“最终错误”混淆的问题。

---

## 6. 工作流主执行顺序

`CompileWorkflowRunner.run()` 的主流程如下：

```13:59:/workspace/deer-flow/backend/packages/harness/deerflow/compile/workflow/runner.py
class CompileWorkflowRunner:
    def run(self, workflow_input: CompileWorkflowInput) -> CompileWorkflowResult:
        state = self._init_state(workflow_input)
        session = None
        services = get_compile_services()

        try:
            session = run_prepare_stage(state, workflow_input)
            services.manager.log_event(session, "workflow.stage.started", stage="clone")
            run_clone_stage(state, workflow_input, session)
            services.manager.log_event(session, "workflow.stage.completed", stage="clone", status=state.status)
            services.manager.log_event(session, "workflow.stage.started", stage="inspect")
            run_inspect_stage(state, session)
            services.manager.log_event(session, "workflow.stage.completed", stage="inspect", status=state.status, build_system=state.build_system)
            services.manager.log_event(session, "workflow.stage.started", stage="build")
            run_build_stage(state, session, workflow_input)
            services.manager.log_event(session, "workflow.stage.completed", stage="build", status=state.status, attempts=len(state.attempts))
            services.manager.log_event(session, "workflow.stage.started", stage="verify")
            run_verify_stage(state, session, workflow_input)
            services.manager.log_event(session, "workflow.stage.completed", stage="verify", status=state.status, artifact_count=len(state.artifacts))
            state.status = "completed"
```

可以概括为以下固定顺序：

1. `prepare`
2. `clone`
3. `inspect`
4. `build`
5. `verify`
6. `finalize`

如果中途异常：

- 会进入 `except`
- 根据当前情况把 `state.status` 设为 `failed` / 保留 `build_failed` / `verify_failed`
- 把真正的未恢复错误写进 `state.final_error`
- 最终一定会进入 `finally` 调 `run_finalize_stage(...)`

所以：

> `finalize` 是兜底阶段，正常或异常都会执行。

---

## 7. 状态流转图

下面是简化后的状态流转：

```text
pending
  ↓ prepare
ready
  ↓ clone 成功
source_ready
  ↓ inspect
inspected
  ↓ build 开始
building
  ↓ build 成功
build_completed
  ↓ verify
artifacts_verified
  ↓ runner 统一收尾
completed
```

异常路径：

```text
clone 失败        → failed
build 子代理失败   → failed 或 build_failed
verify 失败       → verify_failed（当前实现中较少显式触发）
任意未捕获异常     → failed
```

最终无论成功失败，都会进入：

```text
finalizing → finalized=True（state 标记）
```

注意：

- `finalized=True` 是 state 内部标记，不等于 `status="completed"`。
- `status` 是业务状态；`finalized` 是流程收尾状态。

---

## 8. 各阶段详细机制

### 8.1 Prepare 阶段

实现位置：`run_prepare_stage()`

```25:36:/workspace/deer-flow/backend/packages/harness/deerflow/compile/workflow/stages.py
def run_prepare_stage(state: CompileWorkflowState, workflow_input: CompileWorkflowInput):
    session = prepare_compile_session_impl(
        thread_id=workflow_input.thread_id,
        repo_url=workflow_input.repo_url,
        branch=workflow_input.branch,
        task_description=workflow_input.task_description,
        owner_id=workflow_input.owner_id,
    )
    state.session_id = session.session_id
    state.status = "ready"
    state.prepare_done = True
    return session
```

#### 输入
- `state`
- `workflow_input`

#### 调用的底层操作
- `prepare_compile_session_impl(...)`

#### 底层行为
`prepare_compile_session_impl()` 会：

1. 创建 compile session 目录结构
2. 生成 `session_id`
3. 持久化 `session.json`
4. 创建编译容器
5. 记录 `prepare.started` / `prepare.completed` 日志事件
6. 将 session 状态改为 `ready`

#### 输出
- 返回 `session`
- 更新 `state.session_id`
- 更新 `state.status = "ready"`
- 更新 `state.prepare_done = True`

---

### 8.2 Clone 阶段

实现位置：`run_clone_stage()`

```39:50:/workspace/deer-flow/backend/packages/harness/deerflow/compile/workflow/stages.py
def run_clone_stage(state: CompileWorkflowState, workflow_input: CompileWorkflowInput, session) -> None:
    result, message = clone_repository_impl(
        session=session,
        repo_url=workflow_input.repo_url,
        branch=workflow_input.branch,
    )
    state.clone_done = True
    state.summary = message
    if result.exit_code != 0:
        state.status = "failed"
        state.final_error = result.combined_output[:4000] or message
        raise RuntimeError(message)
    state.status = "source_ready"
```

#### 输入
- `session`
- `repo_url`
- `branch`

#### 底层行为
`clone_repository_impl()` 会：

1. 在容器内执行 `git clone`
2. 写 `001_clone.log`
3. 记录一条 `BuildCommandRecord(stage="clone")`
4. 失败则标记 session `failed`
5. 成功则探测 commit SHA，并把 session 状态更新为 `source_ready`

#### 输出
成功时：
- `state.clone_done = True`
- `state.summary = "Repository cloned successfully ..."`
- `state.status = "source_ready"`

失败时：
- `state.clone_done = True`
- `state.status = "failed"`
- `state.final_error = clone 输出`
- 抛异常中断后续阶段

---

### 8.3 Inspect 阶段

实现位置：`run_inspect_stage()`

```53:57:/workspace/deer-flow/backend/packages/harness/deerflow/compile/workflow/stages.py
def run_inspect_stage(state: CompileWorkflowState, session) -> list[str]:
    primary_system, _, suggested_commands = inspect_build_system_impl(session=session)
    state.build_system = primary_system
    state.inspect_done = True
    state.status = "inspected"
    return suggested_commands
```

#### 输入
- `session`

#### 底层行为
`inspect_build_system_impl()` 会检查 marker 文件：

```10:14:/workspace/deer-flow/backend/packages/harness/deerflow/compile/operations.py
_BUILD_SYSTEM_MARKERS = {
    "cmake": "CMakeLists.txt",
    "make": "Makefile",
    "autotools": "configure",
}
```

它会：

1. 在容器里检查这些文件是否存在
2. 推断主构建系统
3. 生成建议命令列表
4. 更新 session.build_system
5. 将 session 状态标记为 `inspected`

#### 输出
- `state.build_system`
- `state.inspect_done = True`
- `state.status = "inspected"`
- 返回 `suggested_commands`，但当前 runner 未继续消费这份返回值

---

### 8.4 Build 阶段

实现位置：`run_build_stage()`

这是整个 workflow 最复杂的阶段，因为它不是直接执行单个命令，而是把“如何构建”交给一个 **compiler subagent**。

#### 4.1 子代理 prompt 与执行目录约束

`run_build_subagent_once()` 里会生成 prompt：

```23:40:/workspace/deer-flow/backend/packages/harness/deerflow/compile/workflow/build_subagent_runner.py
def _build_prompt(workflow_input: CompileWorkflowInput, build_system: str | None) -> str:
    payload = {
        ...
        "working_directory": "/workspace/repo",
    }
    return (
        "Complete the build stage for the already prepared compile session. "
        "Use run_compile_command for all actions. "
        "Unless you have a specific reason not to, run commands from the repository root '/workspace/repo' and avoid prefixing every command with 'cd /workspace/repo &&'. "
        ...
    )
```

这意味着 build 阶段现在已经明确强化了：

- 默认在 `/workspace/repo` 下执行
- 尽量不要反复手写 `cd /workspace/repo &&`

这样做的目的：

- 降低子代理重复处理目录切换的负担
- 统一 attempts 中命令格式
- 减少容器内部路径在 summary/attempts 中的泄漏强度

#### 4.2 子代理结果 JSON 契约

```20:24:/workspace/deer-flow/backend/packages/harness/deerflow/compile/workflow/build_subagent_runner.py
_BUILD_RESULT_JSON_SCHEMA = {
    "type": "object",
    "required": ["build_status", "proceed_to_verify", "summary", "artifacts"],
}
```

要求：

- `build_status`：只能是 `success` / `failed`
- `proceed_to_verify`：布尔值
- `summary`：必须有
- `artifacts`：必须是字符串数组
- 成功时必须至少提供一个 artifact 路径

#### 4.3 Build 阶段如何回填 state

build 子代理完成后：

1. 重新加载 session
2. 把新增的 `session.commands` 转成 `BuildAttempt`
3. 把新增 log 加入 `state.logs`
4. 解析子代理 JSON
5. 如果构建成功且允许 verify：
   - 规范化 artifact 路径
   - 调 `record_build_artifact_impl()` 记录产物
   - 更新 `state.artifacts`
   - 设置 `state.build_done = True`
   - 设置 `state.status = "build_completed"`
6. 否则把错误写入 `state.final_error` 并抛错

#### 输入
- `state.build_system`
- `workflow_input` 中的 `artifact_hint` / `build_goal` / `max_build_attempts`
- 已准备好的 `session`

#### 输出
成功时：
- `state.status = "build_completed"`
- `state.build_done = True`
- `state.summary = 子代理 summary`
- `state.attempts += 新增命令记录`
- `state.logs += 新增日志路径`
- `state.artifacts = 新记录产物`

失败时：
- `state.final_error = 错误原因`
- 抛异常进入 runner 的 `except`

---

### 8.5 Verify 阶段

实现位置：`run_verify_stage()`

```120:129:/workspace/deer-flow/backend/packages/harness/deerflow/compile/workflow/stages.py
def run_verify_stage(state: CompileWorkflowState, session, workflow_input: CompileWorkflowInput) -> None:
    _, artifacts, message = verify_build_artifacts_impl(
        session=session,
        file_pattern=workflow_input.artifact_hint,
        copy_to_artifacts=False,
    )
    state.verify_done = True
    state.verify_message = message
    state.artifacts = artifacts
    state.status = "artifacts_verified"
```

#### 输入
- `session`
- `artifact_hint`

#### 当前实际行为
虽然 verify 阶段名字叫“校验产物”，但当前实现是一个**占位/简化版实现**。

`verify_build_artifacts_impl()` 当前并不会真正进行复杂校验，而是：

- 记录 `verify.started`
- 写一条 `verify` 命令记录，命令固定为 `true`
- 返回 `Verification skipped.`
- 把状态标记为 `artifacts_verified`

因此：

- `state.verify_message` 目前更像“阶段占位说明”
- 不能把 `artifacts_verified` 完全等同于“经过严格验证”

---

### 8.6 Finalize 阶段

实现位置：`run_finalize_stage()`

finalize 负责：

1. 用最终 `state.summary` 和 `state.status` 回写 session
2. 生成 `repro/build.sh`
3. 汇总所有日志路径到 `state.logs`
4. 收集 repro 文件到 `state.repro_files`

同时，runner 在进入 finalize 前也会记录：

- `workflow.finalizing`
- 其中额外带上 `warnings` 与 `final_error`

这样在复盘时，`workflow.log` 能区分：

- 最终失败原因
- 普通告警信息

---

## 9. BuildAttempt / attempts 的来源

`attempts` 不是状态机每一步事件，而是**构建阶段新增的命令记录摘要**。

定义如下：

```21:31:/workspace/deer-flow/backend/packages/harness/deerflow/compile/workflow/schemas.py
@dataclass
class BuildAttempt:
    stage: str
    command: str
    exit_code: int | None = None
    summary: str | None = None
    log_path: str | None = None
```

也就是说：

- `workflow.log` 里的各种 `workflow.stage.started/completed` 事件 **不会直接出现在 attempts 里**。
- `attempts` 只关注构建中真正执行过的命令记录。

---

## 10. 最终结果如何从 state 转成 result

`CompileWorkflowRunner._to_result()` 负责把 state 聚合为最终 result：

```69:91:/workspace/deer-flow/backend/packages/harness/deerflow/compile/workflow/runner.py
    def _to_result(self, state: CompileWorkflowState) -> CompileWorkflowResult:
        artifact_paths = [artifact.path for artifact in state.artifacts]
        ...
        return CompileWorkflowResult(
            status=state.status,
            summary=state.summary or default_summary,
            session_id=state.session_id,
            build_system=state.build_system,
            attempts=state.attempts,
            artifacts=artifact_paths,
            logs=state.logs,
            repro_files=state.repro_files,
            verify_message=state.verify_message,
            warnings=state.warnings,
            final_error=state.final_error,
        )
```

关键点：

- `artifacts` 输出的是 session 中记录的产物路径
- `summary` 优先使用 workflow 中累计写入的 `state.summary`
- `warnings` 和 `final_error` 被单独输出，不再混在一个 `error` 文本里

---

## 11. 工具层最终输出格式

`run_compile_workflow` 工具本身不返回 dataclass，而是把 result 格式化为字符串：

```49:70:/workspace/deer-flow/backend/packages/harness/deerflow/tools/builtins/compile_workflow_tool.py
    lines = [
        f"Compile workflow {result.status}.",
        f"Summary: {result.summary}",
        f"Session: {result.session_id or 'unknown'}",
        f"Build system: {result.build_system or 'unknown'}",
        f"Attempts:\n{attempts_summary}",
        f"Artifacts (user-visible session paths):\n{artifact_summary}",
        f"Logs:\n{log_summary}",
        f"Repro files:\n{repro_summary}",
        f"Warnings:\n{warning_summary}",
    ]
    if result.verify_message:
        lines.append(f"Verify: {result.verify_message}")
    lines.append(f"Final error: {result.final_error or 'none'}")
```

新的最终返回相比旧版有三个明显变化：

1. `Artifacts` 文案明确强调：**这是 user-visible session paths**
2. 增加了 `Warnings`
3. `Error` 改成了更明确的 `Final error`

这会减少 `lead_agent` 出现以下误判：

- 把容器路径当成用户路径
- 把已恢复错误当成最终失败

---

## 12. 工作流日志与状态机事件的关系

工作流内部会通过 `CompileSessionManager.log_event()` 不断写 `workflow.log`，记录：

- `workflow.stage.started`
- `workflow.stage.completed`
- `workflow.failed`
- `workflow.finalizing`
- prepare/clone/build/verify/finalize 等底层事件

这套日志**用于排查和复盘**，但不是 `run_compile_workflow` 返回给 `lead_agent` 的内容本体。

换言之：

- `workflow.log` = 内部事件时间线
- `CompileWorkflowResult` = 最终聚合结果
- `run_compile_workflow` 返回字符串 = 给 LLM 消费的最终总结

---

## 13. 当前实现中的几个重要语义特点

### 13.1 最终返回聚焦“结果汇总”，不是“状态流”
这是本工具最核心的对外语义。

### 13.2 Build 阶段依赖编译子代理
真正的构建命令不是 workflow 写死，而是由 `compiler` subagent 根据仓库与 build system 决策。

### 13.3 Build 阶段已强化 repo 根目录执行约束
这减少了目录切换噪声，也更符合“工作目录由框架约束，而不是由 LLM 反复记忆”的原则。

### 13.4 Verify 阶段当前仍是简化实现
虽然状态名叫 `artifacts_verified`，但当前 verify 主要是占位式逻辑，返回 `Verification skipped.`。

### 13.5 最终返回协议已做初步分层
已经开始区分：

- `warnings`
- `final_error`
- `Artifacts (user-visible session paths)`

但还没有完全进化为稳定 JSON 契约。

---

## 14. 现状问题与改进建议

### 14.1 内部状态机偏细，但最终返回协议曾经过粗
workflow 内部同时维护：

- `status`：如 `ready` / `source_ready` / `inspected` / `building` / `build_completed` / `artifacts_verified` / `completed`
- 一组布尔标记：`prepare_done` / `clone_done` / `inspect_done` / `build_done` / `verify_done` / `finalized`

这套状态对内部排查有价值，但对 `lead_agent` 的最终消费来说偏细。真正的问题不是状态多，而是：

- 内部状态很多
- 最终返回若过于依赖自由文本 summary，就容易误导上层

### 14.2 旧版返回容易产生三类误导

1. **容器路径泄漏**
   - summary 容易出现 `/workspace/repo/ffmpeg`
   - `lead_agent` 容易把它错当成用户路径

2. **历史错误和最终错误混淆**
   - 中途恢复的失败容易整体塞进 `Error:`
   - 上层可能误判为最终失败

3. **结果结构不稳定**
   - 高度依赖子代理 summary 的自由文本质量

### 14.3 本轮代码调整的思路

本轮已按以下方向修改：

1. **build prompt 强化 repo 根目录执行约束**
2. **最终返回增加 `Warnings` / `Final error` 分层**
3. **artifacts 文案明确强调 user-visible session paths**

### 14.4 后续仍建议推进的优化

虽然本轮已经改善了最终返回协议，但后续仍建议继续推进：

- 真正实现 `verify_build_artifacts`，而不是 `Verification skipped.`
- 在 workflow 内显式记录“已恢复错误”，自动填入 `warnings`
- 把最终结果进一步收敛为稳定 JSON 契约，再由 `lead_agent` 负责自然语言渲染

---

## 15. 总结

`run_compile_workflow` 的内部 workflow 本质上是一个**固定阶段顺序的编排器**，它把底层编译 session、构建系统探测、编译子代理执行、产物记录、日志汇总和最终收尾串联起来。

其关键特点是：

1. **入口参数简单**：仓库、分支、任务描述、产物提示等。
2. **内部状态明确**：通过 `CompileWorkflowState` 贯穿各阶段。
3. **阶段固定**：prepare → clone → inspect → build → verify → finalize。
4. **构建决策外包给子代理**：workflow 不直接硬编码具体构建命令。
5. **对外只暴露最终结果**：`lead_agent` 拿到的是最终字符串汇总，而不是状态机逐步流转。
6. **本轮已经开始对返回协议做分层**：通过 `warnings`、`final_error`、`user-visible artifacts` 降低误导风险。
7. **后续仍需继续收敛**：尤其是 verify 真正落地，以及最终返回进一步结构化。
