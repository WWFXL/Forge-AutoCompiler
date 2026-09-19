# 编译运行时可靠性改造设计

日期：2026-09-19。状态：**用户已批准实施**。

本设计只覆盖已经确认的四个问题：阶段化 Shell、单 run 单活动 session/container、run 级统一清理、显式 replay recipe。实施必须先创建并回读 GitHub Issue，再修改业务代码。

## 1. 背景与证据

真实 gRPC 编译暴露了以下相互关联的问题：

- 一次 `run_container_bash` 调用混合 configure、build、诊断和日志截取；管道内部已经失败，但末尾 `tail`、`echo` 等命令让整个 Shell 返回 0。
- 同一个 run 先后创建三个 Compile Session，也创建了三个编译容器。前一个 session 的 workspace、依赖和中间产物没有被继续复用。
- 用户终止编译后没有走到模型主动调用的 `finalize_session`，因此 run 拥有的编译容器持续运行。
- replay 从所有成功 Bash 记录推导脚本，诊断命令和带 session 路径的命令也可能进入配方，最终出现 `Invalid replay command containing a host or session path`。
- 日志文件名按命令列表长度生成，并发执行时可能让不同 `command_id` 指向同一个日志文件。

这些问题不能只靠模型“更小心”。提示词负责表达编译策略，工具 schema、状态机和执行器负责强制可验证的不变量。

## 2. 目标

1. 一次 `run_container_bash` 只表示一个逻辑阶段，阶段身份可审计。
2. Shell 中任一未处理的失败都成为工具失败，不被后续输出命令或管道吞掉。
3. 同一 run 在任一时刻最多存在一个非终态 Compile Session，以及与之对应的一个活动编译容器。
4. 同 repo、branch、image 的重复 prepare 幂等返回原 session/container，继续复用 workspace、依赖和中间文件。
5. run 无论成功、异常、用户取消或 recursion exhausted，均由运行时统一回收其拥有的 compile/replay 容器。
6. replay 只执行 Compiler 显式选定、验证通过、最小且可移植的 recipe，不再从全部成功 Bash 自动推导。
7. 每条命令有唯一日志文件，并能通过 `command_id` 稳定追溯。

## 3. 非目标

- 不加入任何“允许非零退出码”的参数、白名单或兼容分支。
- 不解析任意 Shell AST 来判断每一个简单命令；逻辑阶段由工具参数和提示词契约表达，真实退出结果由严格 Shell 执行器保证。
- 不实施 P2 项目 profile、构建文档优先级、子模块优化、依赖缓存或阶段预算。
- 不增加独立 artifact consumer gate。
- 不修改冻结 benchmark manifest、历史 evidence 或已完成 session。
- 不运行正式 provider 实验，也不在本次开发中清理服务器上现存的遗留容器。
- 不保留旧的隐式 replay recipe 调用方式；当前项目没有要求对未发布的内部工具 schema 保持向后兼容。

## 4. 设计原则

- **策略与机制分离**：提示词要求“一次一个逻辑阶段”，执行器保证严格失败传播，状态机保证唯一 session 和资源回收。
- **审计与配方分离**：所有命令都保留在 audit history；只有显式 recipe IDs 决定 clean replay 内容。
- **幂等优先**：prepare、cleanup 和 orphan reconciliation 都允许重复调用，并收敛到相同状态。
- **权威状态优先**：并发或取消路径重新加载 session 后只合并允许变化的字段，不能用 stale 副本复活终态。
- **最小权限清理**：只操作带 Forge ownership labels 且属于目标 run/session 的容器。
- **不猜测 Shell 意图**：工具不靠命令文本猜 build 或 diagnostic；调用者必须显式声明阶段角色。

## 5. 阶段化 Shell

### 5.1 工具契约

`run_container_bash` 增加必填 `role`，只接受：

- `dependency`
- `configure`
- `build`
- `diagnostic`
- `smoke`
- `artifact_stage`

一次调用可以包含完成该阶段所必需的连续 Shell 操作，例如 configure 前清理旧 build 目录；但不能把 configure、build、smoke 和日志截取混在同一次调用中。

Compiler 提示词明确要求：

- 每个逻辑阶段单独调用工具；
- 不用 `| tail`、`| head`、末尾 `echo` 等方式改变关键命令的最终状态；
- 工具已经保存完整日志并返回有界输出，不需要在命令内截断日志；
- 失败后先运行独立 `diagnostic`，再提交修改后的阶段命令；
- 不通过 `|| true`、`if`、`$?` 或类似结构把非零状态转为成功。

### 5.2 执行语义

执行器在临时脚本最前面统一注入：

```bash
set -euo pipefail
```

调用者不能关闭这些选项。执行器记录脚本真实退出码、超时状态、role、完整日志哈希和有限预览。

这能保证：

- `false | tee output.log` 返回非零；
- `false; echo done` 在 `echo` 前停止并返回非零；
- build 失败后不会继续执行同一次调用中的 `tail`。

工具不承诺识别 Shell 内被调用者主动吞掉的错误，因此提示词同时禁止错误容忍结构。本次不新增 `allow_failure`。

## 6. 单 run 单活动 session/container

### 6.1 身份

活动 session 的幂等键为：

```text
run_id + normalized_repo_url + branch + resolved_image
```

其中 `run_id` 是一次 Leader Agent 执行的稳定身份；`session_id` 仍表示持久化编译会话。Compile Session 和所有 compile/replay 容器都记录 `run_id`、`thread_id`、`session_id`、`role` labels。

### 6.2 原子 prepare

`prepare_compile_session` 在同一个 manager lock/transaction 中完成查询与创建：

```text
没有活动 session
  -> 创建 session 和 container

已有相同 repo/branch/image 的活动 session
  -> 返回原 session/container，记录 session.resumed

已有不同请求的活动 session
  -> 拒绝，classification=active_session_conflict

检测到多个活动 session
  -> 拒绝，classification=multiple_active_sessions
```

串行和并发重复 prepare 都必须只产生一个 session/container。活动 session 内的编译失败不自动创建新 session；Compiler 在原 workspace 中诊断和修复。只有 session 已进入终态，新的 prepare 才能创建新 session。

终态集合必须集中定义并被 manager、prepare、finalize、cleanup 和 reconciliation 共用。

## 7. run 级统一清理

### 7.1 生命周期边界

资源回收不能依赖模型是否调用 `finalize_session`。当前两种运行模式分别接入可用的生命周期边界：

```text
标准 LangGraph：compiler task error/cancel/timeout cleanup + Lead 正常 after_agent cleanup
Gateway 内嵌运行时：worker try/finally cleanup all Forge containers owned by run_id
```

Gateway worker 的 `finally` 覆盖正常成功、业务异常、客户端/用户取消和 timeout；compiler task 自身覆盖 recursion exhausted、失败、取消与超时。清理同时处理 compile 和 replay 容器，并在必要时把仍非终态的 session 收敛为明确终态。标准 LangGraph 进程被强制终止时 Python cleanup 可能无法执行；安全 reconciliation 不会删除仍标记为活动且无法证明为 orphan 的容器。

### 7.2 幂等与安全范围

- 按完整 Forge labels 枚举，不按名称前缀或全局 Docker 列表模糊删除。
- 先停止后删除；容器已不存在视为成功。
- 父级取消路径必须等待/对账可能仍在创建容器的 worker，再次按 labels 清理。
- cleanup 只更新终止原因、容器状态和清理证据等允许字段，不覆盖 commit、recipe、artifacts 或 verification。
- 记录 `run.cleanup.started/completed/failed`，失败时包含 remaining container identity，但不得包含凭据或宿主敏感路径。

### 7.3 启动 reconciliation

每次 prepare 前执行严格 Forge-label-scoped orphan reconciliation：只处理有完整 ownership labels、身份与持久化 session 匹配且 session 已终态的 compile/replay 容器。无法证明 ownership 或终态时不删除，并记录可审计结果。

## 8. 显式 replay recipe

### 8.1 提交接口

`submit_build_result` 改为要求：

```json
{
  "supporting_command_id": "command_build",
  "recipe_command_ids": [
    "command_dependency",
    "command_configure",
    "command_build",
    "command_artifact_stage"
  ]
}
```

Compiler 在确认候选产物后，从本 session 的 audit history 中显式选择最小命令序列。recipe 本身持久化命令 ID、顺序、role、command/workdir 哈希和生成时间；完整命令仍以 audit record 为单一事实来源。

### 8.2 Recipe 校验

每个 `recipe_command_id` 必须满足：

- 属于当前 session，存在且唯一；
- 按原始执行顺序排列，无重复；
- 执行成功且未超时；
- role 只允许 `dependency`、`configure`、`build`、`artifact_stage`；
- workdir 位于 `/workspace`、`/workspace/repo` 后代或 `/artifacts`；
- 命令不含宿主路径、`.compile-sessions`、`/logs`、`/repro`、session/thread ID；
- 至少包含一个 `build` 和一个 `artifact_stage`；
- `supporting_command_id` 位于 recipe 中、role 为 `build`，并且是最后一个影响候选的成功 build。

`diagnostic`、`smoke`、失败、超时、重复、乱序、跨 session 和不可移植命令一律拒绝。拒绝结果包含稳定 `classification`、`offending_command_id` 和不泄露敏感内容的原因。

### 8.3 Replay 去重

对规范化 recipe IDs、对应 command/workdir 哈希、commit、image ID 和 artifact snapshot 生成 fingerprint。相同 session 中，相同 fingerprint 的确定性 replay 失败不再次执行；只有 recipe 或候选输入变化后才能创建新的 replay attempt。

replay 始终在原始不可变 image ID、新容器、空 workspace 和空 artifacts 中执行：clone 固定 commit，然后严格按 recipe 顺序执行。诊断和 smoke 不进入 build script；产物验证仍由 replay verifier 独立执行。

## 9. 唯一日志身份

执行前先生成随机且稳定的 `command_id`，日志路径固定为：

```text
logs/{command_id}.log
```

不再用 `len(session.commands) + 1` 命名。session 持久化 `command_id -> host log metadata`，工具只返回容器可见路径 `/logs/{command_id}.log` 或不透明日志 ID，避免模型接触宿主绝对路径。

## 10. 状态与证据不变量

- audit history 只追加；recipe 只能通过显式 `recipe_command_ids` 产生。
- 一个 command ID 只对应一个日志文件，一个日志文件只对应一个 command ID。
- 同一 `run_id` 最多一个非终态 session 和一个活动 compile container。
- 终态 session 不会被 stale worker 改回非终态。
- run 结束后，其 Forge compile/replay 容器集合为空；失败时必须记录 remaining identities。
- recipe 每一步都能反查当前 session 的成功 audit record。
- submit supporting build、recipe 和 artifact snapshot 来自同一 session version。
- replay 从固定 commit、不可变 image ID、空 workspace/artifacts 开始。

## 11. 验收标准

### Shell 与阶段

- `false | tee output.log`、`false; echo done`、失败后 `tail` 均得到非零工具结果。
- 每条 command record 都有合法 role；提示词回归明确禁止混合阶段和吞错模式。
- configure、build、diagnostic、smoke、artifact staging 的结果互不覆盖。

### Session 与容器

- 串行重复 prepare 相同请求复用原 session/container。
- 100 个并发相同 prepare 只产生一个 session/container。
- 同 run 的不同请求返回 `active_session_conflict`；已有多个活动 session 返回 `multiple_active_sessions`。
- Lead 正常结束、compiler exception/cancel/timeout/recursion exhausted 和 Gateway worker 的所有退出路径都触发相应的 run/session cleanup。
- prepare 前 reconciliation 只处理标签完整、身份匹配且 session 已终态的 Forge 容器。

### Recipe 与日志

- recipe 排除 diagnostic、smoke、失败、超时、重复、乱序和不可移植步骤。
- supporting command 必须属于 recipe 且 role 为 `build`。
- 同一确定性失败 fingerprint 不重复启动 replay。
- clean replay 只执行显式 recipe，并能从固定 commit 重新生成候选 artifacts。
- 100 个并发命令产生 100 个唯一日志文件，内容和 command ID 一一对应。

### 回归与边界

- 现有 compile manager、tool、replay、termination 和 Docker runtime 测试通过。
- 新增并发、取消和 replay 回归不调用真实模型 provider。
- 不修改 frozen benchmark manifest/evidence；若实现被证明必须修改，立即停止并请求用户重新决策。

## 12. 已批准决策

- 用户批准“提示词阶段化 + 执行器严格 Shell”双层方案。
- 用户批准同一个 run 复用同一活动 session/container，不因普通编译失败重建环境。
- 用户批准 run 外层统一清理，处理主动终止导致的遗留容器。
- 用户批准 replay 使用显式最小 recipe IDs，不再收集所有成功 Bash。
- 用户明确暂不设计非零退出码容忍。
- 用户明确暂不实施复杂仓库 P2 规则。
