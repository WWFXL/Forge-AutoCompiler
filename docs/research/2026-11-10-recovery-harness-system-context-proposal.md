# 补充真实系统实现后的恢复 Harness 提案（待用户审核）

Issue #723；身份 `cpp-build-offline-recovery-harness-system-context-proposal-v1`。**已向高级模型提供当前科研实现并重新分析一次，得到待审候选 `R2_system_context`。原R2保留，尚未采用新指导，比较0、论文v0.10未改。** 本轮是离线提案与结果分析，不是构建性能实验。

## 本次实际补充与调用

原R2主要得到共同提示、历史恢复材料及人工修复概述，未提供实际工具Schema与关键实现源码。用户明确要求补强后重新分析。本次保持同一13次E53自然恢复交接及3条正常成功边界逐项不变，同时补充：

- PR722合并版本 `64978dd68b86398aa2daa1a44a8755f6b26338a9` 的8个文件、38个完整类/函数/方法定义，附行号与完整文件哈希。
- 实际 `PublicBuildTask`、`SimpleBuildActions` Schema，以及 `list_source/read_source/read_failure_log` 三个只读工具Schema。
- [系统实现说明](2026-11-10-recovery-optimizer-system-context.md)和[执行契约](../compile_workflow_execution.md)：阶段观察、交接、修订、成功依赖保留、后缀失效、独立结果和上下文限制。
- 原R2实际提案作为复核对象，要求在诊断中说明哪些保留、哪些修正；新指导完整替换附加指导，no_change仍表示保留H0。

实现参考单独标为 `implementation_reference_not_trajectory` / `SYS:implementation`，不增加构建效果样本。模型看到的是选定实现片段，不是整个仓库；离线请求没有Bash、源码浏览或联网工具。当前线上科研规划/恢复也只有只读工具和方案输出，由Workflow执行命令，不能混入产品compiler、强工具Agent或另行研究过的局部执行恢复能力。

用户本次新指令授权一次独立复分析，自限共享原1美元与UTC2026-11-10 14:24:13—18:24:13窗口，旧费用0.106807美元计入累计，不重置时窗。执行revision `d8109763`，请求SHA `3b5157ab7310f9c4f2ba5a2e7f7c5461ab5510dbe2318831a49db8cf88387e18`，材料431278 UTF-8字节。实际一次RichLab `gpt-6.1-sol`，同名响应，137574输入/2040输出/139614总Token，61.8010秒，估费 **0.139614美元**；两次共享累计 **0.246421美元**。依据用户输入/输出各1美元/百万Token报价，非官方账单，响应标识不独立证明后端。无自动重试、未知用量0，未另做服务探测。

## 高级模型怎样修正原R2

以下为模型原诊断的归纳，[完整JSON](../../benchmarks/fixtures/recovery-harness-system-context-gpt61sol-v1/proposal.json)保持原文，不把模型解释当成已证实的因果结论。

| 复核项 | 原R2 | 补充实现后的实际提案 |
| --- | --- | --- |
| 外部依赖修订是否可表达 | 建议获取、配置、编译、安装拆成dependency，放主配置之前 | 明确撤去这个通用模板：执行器检查实际命令，改角色标签不保证合法，仓库外临时目录也未授权；只保留按具体拒绝修正关联约束 |
| 网络失败能否换路径 | “不因网络超时切换构建入口”的限制较强 | 允许作者支持且确能处理当前阻塞的备用获取路径/构建入口；保留主组件与默认范围，不能假设拆包安装解决索引失败 |
| 重读与上下文 | 按实际错误局部补读，但容易被理解为仅新日志才可再读 | 明确允许补读因截断或压缩缺失的必要区间；只减少仍可见且相同的重复确认，不给必要读取设固定次数 |
| 已有底座与新增策略 | 多次重述依赖保留、目录观察、纠正和分层结果 | 识别这些已实现，删减重复说明；指导重点放在证据缺口、合法修订和及时提交，不计共同机制为候选能力 |
| 版本探测及阻塞结束 | “明确说明阻塞”没有对应接口细节 | 说明Agent不能亲自试命令或调用不存在的终止工具；版本守卫须写进交给Workflow的动作，无合法方案时仍可能由现有错误/预算机制结束 |
| 兼容开关 | 沿失败符号确认已有配置机制与目标关系 | 保留；证据充分即提交，不能因主库局部成功而关闭默认目标或测试。历史两法均成功，不证明指导优势 |

其中第一项能直接由 `validate_phase_command`、`infer_command_roles` 和目录校验支持；新的候选至少避免了原建议中一个未获实现支持的通用步骤模板。但不能仅从提示变得更贴合接口，推断其成功率、费用或时间改善。E53来自共同修复前，没有把它重新标成修复后的观察。

## 新恢复指导原文

以下为模型原文，未人工删改：

```text
以最近交接中实际到达的步骤和直接错误选择修订，区分已执行失败、执行前拒绝、旧日志与未执行后缀。补读前明确尚缺哪条会影响动作选择的证据；已有材料足够时提交，不必先写账本。

沿失败文件、符号或规则补读。截断或上下文压缩使必要内容缺失时，从缺失位置读取；新日志、错误归属不明或新的故障允许再次读取。已经完整取得且仍可见的相同片段无需重复确认。必要的依赖和目标关系读取不受固定次数限制。

获取失败先区分索引更新、包下载和安装。后续安装的拆分不能自动解释为解决前面的下载阻塞。通常保留已有依据的依赖集合及未执行后缀；如需改变获取路径或构建入口，补齐它如何处理当前阻塞、为何保持主要组件和默认范围的依据，再提出修订。工具存在不自动表示能力或版本满足；相关守卫只能作为有依据、交由Workflow执行的动作，不能宣称已亲自探测。

编译兼容故障可追踪作者或内置依赖已有的配置机制，确认定义、控制失败代码的条件及受影响目标。证据足以说明兼容修改且默认目标和测试保持时即提交，不因主库局部成功缩减剩余目标。

收到结构或策略拒绝时，保留已读证据，检查受影响动作的关联阶段、目录、ID及引用约束后修正。外部依赖的配置和编译不能仅靠标为dependency获得放行；不要用包装Shell或更换临时路径绕过约束。所有修订通过现有结构化接口提交，由Workflow执行并反馈。reason简短区分已观察事实、拟执行动作和仍缺的依据；无法支持合法修订时如实说明限制，不编造可执行动作或专用终止接口。
```

## 提示长度与效果边界

| 当前共同提示下的方案 | 附加指导UTF-8字节 | 完整恢复提示UTF-8字节 |
| --- | ---: | ---: |
| H0 | 0 | 4093 |
| R1原指导参照 | 1677 | 5901 |
| 原R2 | 2551 | 6775 |
| R2_system_context | 1817 | 6041 |

新指导比原R2少734字节/28.8%，但仍比R1多140字节、比H0有额外上下文。字节减少不等于同等比例的Token或费用减少，更不能预称恢复轮数下降。两次分析还受模型生成差异与明确复核指令影响，本轮不是“加实现上下文”的因果消融。

待审核的剩余取舍：新指导主要调证据与提交策略，不扩展复杂外部依赖构建的表达能力；当前没有专用阻塞结束接口。它不能保证绕开全部Workflow兼容性问题，也不承诺修复网络服务。本轮不顺带增加这些接口或修改共同底座。

完整提示：[H0](../../benchmarks/fixtures/recovery-harness-system-context-gpt61sol-v1/prompt-H0.txt)、[R1参照](../../benchmarks/fixtures/recovery-harness-system-context-gpt61sol-v1/prompt-R1.txt)、[原R2](../../benchmarks/fixtures/recovery-harness-system-context-gpt61sol-v1/prompt-R2-original.txt)、[新候选](../../benchmarks/fixtures/recovery-harness-system-context-gpt61sol-v1/prompt-R2-system-context.txt)。完整差异：[H0→新候选](../../benchmarks/fixtures/recovery-harness-system-context-gpt61sol-v1/diff-H0-R2-system-context.patch)、[R1→新候选](../../benchmarks/fixtures/recovery-harness-system-context-gpt61sol-v1/diff-R1-R2-system-context.patch)、[原R2→新候选](../../benchmarks/fixtures/recovery-harness-system-context-gpt61sol-v1/diff-R2-original-R2-system-context.patch)。R1是当前底座上的指导参照，不冒充历史原请求。

## 验证、原件与停止点

17项新旧提案脚本相关检查通过，修改文件Ruff/格式通过；核验原16条材料不变、真实源码片段、工具权限、累计计费、失败保存和不重试。pytest退出时报告旧临时构建目录清理权限警告，与本轮无Docker执行无关，未为此改变旧数据或扩测。未追加Docker实建或本地产品全测，相关检查不能算模型效果。

- 新候选SHA：`270becfd8fe2c0c89d0d7ab8c820893cdc6ae7cdd9d2c50e95ecb11f84263743`，共同提示仍为`e35f082d179d0ac9014c5b2f59d823e30cb81e0f65439e8982af47cf446c63f3`。
- 新原件：`/home/yiwei/.codex/outputs/forge-recovery-harness-system-context-gpt61sol-20261110-v1/`，包含请求/原响应/授权/费用/诊断/候选/差异和源码快照；28文件，typed inventory `f38232f896b32d097ac8666d8367a436d5c77015586de410b61a3c5493dae241`。
- 会话收据：`/home/yiwei/.codex/outputs/forge-recovery-harness-system-context-session-20261110-v1/`；Git可读副本为`benchmarks/fixtures/recovery-harness-system-context-gpt61sol-v1/`，输入为独立`recovery-harness-system-context-v1/`。
- 原R2及其inventory0805db01、E53 inventory235feccd、全部历史失败和分母完整保留。

本次独立调用结束，无活动Provider，余额不扩批。停止在用户审核新指导：审核后另下比较指令，结果另审并同意后才入文。H0仍默认，初始规划、Flash、工具/Workflow/验证器和论文v0.10不变。知识库只经MCP同步，不进入正式实验Agent上下文。
