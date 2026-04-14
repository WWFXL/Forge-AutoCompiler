# Compile Workflow + Build Agent 改造任务总结

## 一、任务背景

本轮任务的目标，是把 deerflow 当前“远程仓库编译”能力从**纯 compiler 子代理驱动**，调整为**workflow 固定主干 + build agent 负责构建决策**的架构。

在原有模式下，`compiler` 子代理需要通过 prompt 自己记住并执行完整流程，包括：

- 准备编译 session
- 拉取仓库
- 检测构建系统
- 执行编译
- 校验产物
- 最终清理 session

这种方式的主要问题在于：

- 流程顺序依赖 prompt 和记忆，稳定性不足
- `finalize` 这类收尾动作容易遗漏
- 低层流程控制和智能决策耦合过紧
- lead agent 只能通过 compiler subagent 间接接入编译能力

因此，本轮改造的核心思路是：

- **把确定性流程收回到代码中**
- **把智能性收敛到 build 阶段**
- **保留现有 compile tools 和 compiler subagent 的大部分资产**
- **采用尽量小的改动完成架构迁移**

---

## 二、设计思路

### 1. 整体架构目标

新的架构分成两层：

#### 外层：Compile Workflow

由代码固定控制主干阶段，按顺序执行：

1. prepare session
2. clone repository
3. inspect build system
4. build stage
5. verify artifacts
6. finalize session

这层负责：

- 流程顺序保证
- 状态记录
- session 生命周期控制
- 失败后的统一处理
- finalize 必执行
- 最终结果聚合

#### 内层：Build Agent

只在 build 阶段参与，负责：

- 选择下一步构建动作
- 分析失败日志
- 决定依赖安装、配置调整或继续编译
- 控制有限次数内的多轮尝试
- 在必要时停止

这层不负责：

- 创建 session
- clone 仓库
- verify 产物
- finalize 收尾

---

### 2. 与原有 deerflow 能力的关系

本轮设计遵循“不要重复造轮子”的原则：

- 保留现有 compile tools
- 保留现有 compile session manager / docker runtime
- 保留现有 compiler subagent 文件
- 复用 deerflow 现有 agent 能力栈来实现 Build Agent

最终目标不是删除原有系统，而是在原有能力基础上收拢职责边界。

---

### 3. 关键判断原则

本轮实现过程中冻结了以下原则：

- 编译主入口改为高层 workflow 工具
- build 阶段允许使用完整 agent 决策
- build agent 允许通过受控命令面执行依赖安装
- verify 没找到明确产物时，整体视为失败
- 旧的 `compiler_agent.py` 暂时保留，不强制下线

---

## 三、本轮改动总览

### 1. 抽离 compile 内部执行层

首先将原本直接写在工具函数中的核心逻辑，抽成 compile 内部可直接调用的执行层。

这样做的目的，是让后续 workflow runner 能直接调用 Python 内部实现，而不是依赖 tool runtime 机制来“模拟调用工具”。

这一步之后，compile 相关能力形成了两层：

- 对外的 tool 接口
- 对内的 operations / impl 执行层

从而为 workflow 接管流程控制打下基础。

---

### 2. 新增 compile workflow 模块

新增了 compile workflow 目录，建立了 workflow 的基本骨架，包括：

- workflow 输入结构
- workflow 状态结构
- workflow 结果结构
- 各阶段 stage 函数
- runner 统一执行入口

这一步把原来依赖子代理 prompt 才能维持的流程顺序，改成了由代码明确保证。

workflow 现在成为编译系统的主控制器。

---

### 3. 建立高层入口 `run_compile_workflow`

新增了一个高层工具入口，用于让 lead agent 直接触发编译 workflow。

这一步的意义是：

- lead agent 不再必须通过 `task(..., subagent_type="compiler")` 才能进入编译能力
- 编译工作流具备了统一、稳定的单入口
- 后续可以更容易地把 lead agent 的编译意图直接绑定到 workflow 上

---

### 4. 将 build 阶段升级为 Build Agent 决策循环

在 workflow 骨架建立之后，将原本的“默认命令占位构建逻辑”升级为 build agent 驱动。

新的 build 阶段机制是：

- workflow 把当前上下文组织成 build agent 输入
- build agent 给出结构化决策
- workflow 执行决策中的命令
- 如果失败，将失败摘要回传给下一轮决策
- 在有限轮数内持续迭代
- 达到限制或 agent 决定停止时结束

这一步完成后，系统正式实现了：

- workflow 固定主干
- agent 只控制 build 阶段

---

### 5. 明确 verify / success / failure 语义

本轮重点强化了最终结果的定义，尤其是成功条件。

新的规则是：

- 仅 build 命令执行成功，不代表 workflow 成功
- 必须在 verify 阶段找到明确产物
- 如果 verify 没找到产物，则整体结果为 failed

同时，workflow 结果中也补充了：

- verify 阶段摘要
- attempts 列表
- artifacts 列表
- logs 列表
- repro 文件信息

这样 lead agent 或用户在消费结果时，能更清楚地看出失败发生在哪一层。

---

### 6. lead prompt 迁移到新入口

在保留旧 `compiler_agent.py` 的前提下，lead prompt 的编译意图指引已经改为：

- 远程仓库编译请求应直接使用 `run_compile_workflow`

这意味着从意图层面，新的主入口已经切到 workflow。

旧 compiler subagent 目前仍保留，但不再是推荐主路径。

---

## 四、改动后的系统职责边界

### Lead Agent

负责：

- 识别用户是否要编译远程仓库
- 提取高层参数
- 直接调用 `run_compile_workflow`

不负责：

- 编译流程排序
- 构建失败后的低层诊断
- session 生命周期控制

### Compile Workflow

负责：

- 固定执行顺序
- session 生命周期管理
- 状态记录
- 将 build 上下文喂给 build agent
- 聚合最终结果
- 保证 finalize 执行

### Build Agent

负责：

- 决定下一条构建相关动作
- 处理依赖安装、配置调整、重新构建等决策
- 在失败上下文下进行多轮迭代

不负责：

- session 创建
- clone
- verify
- finalize

---

## 五、本轮改造后的收益

### 1. 流程稳定性更强

原来依赖 prompt 和记忆的流程主干，改成了代码强控制的 workflow，顺序与状态更稳定。

### 2. finalize 不再依赖 prompt 记忆

现在 `finalize` 由 workflow 在 `finally` 中保证执行，避免了收尾遗漏。

### 3. 智能与控制边界更清晰

workflow 负责确定性主干，build agent 只负责构建决策，职责比之前清晰得多。

### 4. lead agent 接入更直接

lead agent 现在可以直接走高层 compile workflow，而不是必须通过旧 compiler subagent 间接进入。

### 5. 失败语义更明确

“无产物即失败”已经体现在 workflow 结果层，而不是只看 build command 是否成功。

---

## 六、当前版本的定位

当前这一版可以视为**compile workflow + build agent 架构的第一版落地实现**。

已经完成的，是主干架构迁移；尚可继续优化的，主要是工程完善度，例如：

- Build Agent 与 deerflow 标准 subagent 执行封装的一致性还可进一步收拢
- Build Agent 输出的结构化解析健壮性还可继续增强
- compile-container 内的只读辅助工具未来可按需补充
- 仍需要通过真实仓库编译任务做更多端到端验证

因此，这一版的意义是：

- 已完成架构方向切换
- 已具备真实联调基础
- 后续可以围绕真实编译测试继续迭代细节

---

## 七、总结

本轮任务完成了 deerflow 编译能力从“compiler 子代理自由编排全流程”到“workflow 固定主干 + build agent 负责构建决策”的第一版改造。

这次改造没有推翻原有 compile 系统，而是在已有 compile tools、session manager、docker runtime 和 agent 能力栈基础上完成了职责重组。

最终结果是：

- 编译流程主干由代码保证
- build 阶段仍保留智能决策能力
- lead agent 接入路径更直接
- 结果语义更清晰
- 旧 compiler subagent 保留兼容

这为后续前后端联调、真实仓库验证和进一步工程化完善提供了稳定基础。

