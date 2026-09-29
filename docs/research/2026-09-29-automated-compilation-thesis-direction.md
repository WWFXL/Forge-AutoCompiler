# 自动化编译毕业论文方向：文献定位与研究问题候选

日期：2026-09-29
状态：论文问题冻结前候选
工作类型：结果分析（0 Provider、0 新实验、0 冻结 evidence 写入）

## 1. 研究目标与当前判断

本课题的目标是围绕自动化编译形成一篇范围适中、证据闭合的毕业论文。Forge-AutoCompiler 已具备
Agent Workflow Node、Lead/Compiler Multi-Agent、Compile Session、产物验证和 clean replay 等基础能力，
但这些能力本身不是足够的新贡献。CXXCrafter 是仓库级 C/C++ 自动构建的直接相关工作之一，也不应被
设定为唯一研究对象或唯一对照。

当前首选方向是：

> **面向自动化编译的契约驱动修复：基于可恢复失败状态、确定性候选验证反馈和分层正确性判定的方法。**

这项工作的可辩护增量不是“第一次使用 verifier、Agent 或结构化反馈”，而是把以下三项组合到自动化
编译场景，并用能够隔离反馈作用的实验设计验证：

1. 用候选合同约束交付物、目标映射、构建来源和功能验收，而不接受 Agent 自报成功；
2. 从同一个已提交失败状态派生 baseline/treatment，在模型、工具、环境和剩余预算相同的条件下，
   只改变是否暴露合同派生的可操作反馈包；
3. 用独立 evaluator 分层判断候选合法性、功能正确性、来源合规和 clean replay，不把“命令退出 0”
   等同于任务成功。

## 2. 检索范围与结论边界

本次定位结合了个人知识库中截至 2026-09-23 的定向论文索引、CXXCrafter/CompileAgent 解读及 Forge
历史机制实验笔记，并在 2026-09-29 核验了下表所列论文的公开版本。检索覆盖仓库级自动构建、构建失败
修复、环境配置、反馈闭环、规格权威和分层评测。

这不是严格系统综述。arXiv API 在检索期间出现 timeout/429，因此补充检索使用了 arXiv 论文页、
OpenAlex 和 Crossref。文献结论只能表述为“在本次检索语料中未发现直接覆盖该组合”，不能表述为
“全球首次”或“现有研究均未涉及”。不同论文的任务、样本和成功判据不同，表中数值不能直接横向排名。

## 3. 相关工作矩阵

| 工作 | 任务与规模 | 反馈、工具或控制 | 成功证据与代表结果 | 与 Forge 的重合和留下的问题 |
| --- | --- | --- | --- | --- |
| [CXXCrafter](https://arxiv.org/abs/2505.21069) | C/C++ 仓库级自动构建，论文报告 587/752 成功 | Parser/Generator/Executor/Judge 闭环，迭代生成 Dockerfile | 构建与目标产物检查；约 78% 是作者协议内结果 | 已覆盖 LLM 自动构建和执行反馈迭代；未直接隔离候选合同反馈的作用，也不是 Forge 必须复现的唯一基线 |
| [CompileAgent](https://arxiv.org/abs/2505.04254) | 真实 C/C++ 仓库级编译 | 固定 Flow、说明检索、错误讨论和工具集成 Agent | 以构建和目标文件为主要判据 | 已覆盖 Workflow 中嵌入 Agent 和多 Agent 诊断；分层来源与独立重放仍可加强 |
| [BuildBench](https://arxiv.org/abs/2509.25248) | 148 个可编译 C/C++ 测试仓库 | OSS-Build-Agent、检索和多次尝试 | 最佳 strict/flexible 为 67.6%/73.0%；GPT-4o 三次平均 strict 为 53.0% +/- 6.8 | 给出更分散的仓库级基准和随机性证据；主要回答 buildability，不隔离拒绝反馈机制 |
| [ComBench](https://arxiv.org/abs/2603.27333) | 真实 C/C++ 仓库级编译错误修复 | 编译诊断、代码探索与补丁修复 | GPT-5 的 compile/semantic/exact-match 为 73%/41%/20% | 直接证明“能编译”和“语义正确”存在系统差距；支持 Forge 保留独立功能 oracle |
| [EnConda-Bench](https://arxiv.org/abs/2510.25694) | 软件工程 Agent 的环境配置 | 按规划、感知、诊断、反馈修复和执行分析轨迹 | 过程级评价，不只看最终成功 | 已覆盖一般性的过程指标；Forge 需要把过程指标绑定到自动化编译合同和失败状态 |
| [GradleFixer](https://arxiv.org/abs/2510.08640) | Android/Gradle 构建修复 | 领域工具替代通用 shell | full-semantics Pass@1 74.0%，shell baseline 54.3% | 已覆盖受限领域工具的收益；“工具受限”不能单独作为 Forge 创新 |
| [EvidenT](https://arxiv.org/abs/2605.08621) | 系统级软件包迭代修复，RISC-V 主实验 219 包 | 外部 Build Service、证据保留、知识检索和迭代编排 | 118/219（53.88%）；无 evidence 为 42/219（19.18%）；适配 CXXCrafter 为 20.55% | 已覆盖 evidence-preserving repair；Forge 的增量需落在同状态干预和更严格的候选/来源/replay 合同 |
| [Repo2Run](https://arxiv.org/abs/2502.13681) | 420 个 Python 仓库的可执行环境构建 | 迭代重建 Dockerfile 并使用测试反馈 | EBSR 86.0%；要求 pytest 能执行，不要求测试通过 | 已覆盖环境重建与执行反馈；不能把其 EBSR 当作功能正确率 |
| [EvoConfig](https://arxiv.org/abs/2601.16489) | 自演化多 Agent 环境配置 | 独立诊断 Agent 产生结构化可操作反馈 | Repo2Run 集合 88.1% vs 86.0%；EnvBench 78.1% vs 71.0% | 已覆盖多 Agent 诊断和结构化反馈；其 EBSR 不验证测试语义 |
| [PhantomRun](https://arxiv.org/abs/2602.20284) | 4,248 个嵌入式项目 CI 编译失败 | 日志、源码、历史修复和多构建基础设施 | 最高 CI pass rate 约 45% | 提供大规模真实失败和 CI oracle；单文件修复及 CI pass 不等于通用语义保持 |
| [跨 ISA Build-bench](https://arxiv.org/abs/2511.00780) | 268 个跨 ISA 软件包构建失败 | 多轮构建反馈，比较完整文件和 patch | 最高 build success 63.19%；完整文件通常更稳，patch 通常更省时省 token，故障类型会改变相对表现 | 已直接覆盖完整重写与增量 patch 的一般比较；该方向需要新的自适应策略才能形成增量 |
| [Exact Feedback Is Not Control](https://arxiv.org/abs/2609.28150) | 文本长度、词汇和组合约束的闭环修订，19 个模型 | 确定性完整 verifier、固定预算、matched-state 干预 | controller-level 最终联合成功率 17.4%--99.8% | 已覆盖 exact feedback 和 matched-state 方法；任务不是自动化编译，Forge 不能声称通用方法首创 |
| [SpecHarness](https://arxiv.org/abs/2609.29921) | Agent 规格遵循与运行时治理 | Agent 只提议，独立规格权威依据合格证据提交状态 | 分离 proposal、validation、commit 和 finalization | 与 Forge 的 authority boundary 高度重合；独立 verifier 或规格签收不能单独作为创新 |
| [FDE-Bench](https://arxiv.org/abs/2609.27571) | 136 个部署环境配置任务 | 纯净环境重建和统一四工具 scaffold | build/readiness/behavior/conformance 四层检查；模型解决率 52.9%--75.0% | 已覆盖 fresh rebuild 和分层程序化判定；Forge 需证明自动化编译特有合同与反馈干预的效果 |

## 4. 不能单独主张的创新

本次检索已找到直接先例，以下表述不能单独作为论文创新：

- 用 LLM 或 Agent 自动编译 C/C++ 仓库；
- 在固定 Workflow 中嵌入 Agent，或使用多个 Agent 诊断构建错误；
- 把原始构建日志反馈给模型并迭代修复；
- 保留 evidence/history，使用领域受限工具或结构化诊断；
- 使用独立 verifier、规格权威、deterministic feedback 或 clean replay；
- 只提出过程级或分层指标，或一般性比较完整文件与 patch。

Forge 可以主张的是针对自动化编译的**领域化组合、可操作实现和实验证据**。论文措辞应使用“提出并验证
一套……方法”或“在本次检索语料中尚未发现同时覆盖……的工作”，避免使用“首次”。

## 5. Forge 已有证据资产

### 5.1 `artifact_staging_missing` 机制 pilot

- Behavioral v2 在同一个 CMake checkpoint 上得到 baseline 3/6、treatment 5/6，配对差为 `+2/6`；
  这是单 provider、单仓库、单 controlled fault 的探索性结果。
- Multi-checkpoint v3 覆盖 CMake、Make、Autotools 三个 case，baseline 4/6、treatment 6/6，case 等权
  macro-average 为 0.667 vs 1.000；三个 case 仍属于同一个 `artifact_staging_missing` fault family。

这些结果支持“结构化合同拒绝反馈可能促进候选转换”的可行性，不支持总体 treatment effect、显著性或
自然失败外推。

### 5.2 `opaque_build_provenance` 独立 replication

- 12/12 pairs 均形成终态，但 7/12 endpoint-censored；baseline 为 0/12 provenance conversion，
  treatment 为 6/12 conversion，六次 clean replay 全部通过。
- 只有五个 pair 可进入配对机制估计，差值为 `[+1, +1, +1, 0, 0]`；只有 2/6 project blocks 完整，
  因此 `primary_test=null`。

该批证据证明机制可以到达候选验证和 clean replay，但高删失使确认性总体效应不可估计。不得把 6 次
treatment conversion 写成确认性结论。

### 5.3 Stage C v8 工程 canary

四个固定任务均达到 strict、S0--S5、bitwise 和 cleanup 4/4；`libjpeg-turbo` 出现一次
`target_mapping_invalid -> 同 attempt 修复 -> 成功`。这证明现有 Agent Workflow、pre-freeze verifier、
external evaluator 和 clean replay 能端到端闭合，只提供四任务工程 canary 与单条修复轨迹，不是方法对照。

### 5.4 生产候选合同

生产 verifier 已能给出确定性、有界、结构化的候选拒绝原因：

- delivery unavailable、invalid 或 zero-byte；
- undeclared compiled artifact；
- target mapping/path mismatch；
- functional oracle failure；
- 最多返回 12 个相关路径。

候选通过后，external evaluator 仍独立检查 artifact、functional oracle、provenance 和 clean replay。这些能力
使下一步可以聚焦研究问题和实验识别，而不需要重新建设一套编译 Agent。

## 6. 候选方向比较

下表评分为 1--5 的设计判断，只用于排序，不是实验结果。`证据适配`表示 Forge 现有实现与历史观测能否
直接支持；`新颖性可辩护`表示在本次检索语料中的相对空间；`新增成本`分数越高表示成本越低。

| 候选方向 | 证据适配 | 新颖性可辩护 | 新增成本 | 主要风险 | 定位 |
| --- | ---: | ---: | ---: | --- | --- |
| 契约驱动反馈 + state-matched checkpoint | 5 | 4 | 4 | 现有证据集中于两个 fault family，仍需控制删失并扩大失败状态 | **主方向** |
| artifact/provenance/function/replay 分层评测 | 5 | 3 | 5 | FDE-Bench、ComBench、SpecHarness 已有相邻思想，单独作为方法创新偏弱 | 支撑性评测贡献 |
| 按故障类型选择完整重写或增量 patch/session | 2 | 2 | 2 | 跨 ISA Build-bench 已直接比较两种粒度，需要新增选择策略和完整实验 | 暂缓 |

## 7. 研究问题候选与实验骨架

### 主研究问题

> 在相同编译失败状态、模型、工具和预算下，由确定性候选合同验证器生成的最小结构化拒绝反馈，
> 相比普通失败载荷，是否提高合法候选转换率，并减少重复或无效动作？

“合法候选转换”至少要求 continuation 提交候选、候选合同接受、预声明功能 oracle 通过，并在独立干净
环境中重放成功。仅生成命令、构建退出 0、产物存在或 Agent 自报成功均不计为转换。

### 次级问题

1. 效果是否随失败合同类别和构建系统变化，而不是只在 `artifact_staging_missing` 上出现？
2. 结构化拒绝反馈是否改变到首次合法提交的请求数、tokens、墙钟、重复动作和 policy rejection？
3. 如果候选编译成功，它在 artifact、functional oracle、provenance 和 clean replay 四层分别在哪里失败？

### 三臂主要比较

- 实验单位：一个预先冻结、可恢复的编译失败 checkpoint；同一项目的重复只估计随机性，不扩充项目数。
- C0：当前普通失败载荷，不提供新增的合同字段或修复答案。
- T1：确定性 verifier 产生的最小、白名单 finding，包括 code、path、expected 和 actual；不能包含完整命令、补丁或标准答案。
- T2：在 T1 上增加抽象 repair goal，仍不提供具体修复步骤。
- 同源条件：相同 checkpoint、模型 endpoint、工具、执行环境、剩余请求/token/时间预算和终止规则；只允许 feedback projection 不同。
- 主要比较：C0 vs T1；次级比较：T1 vs T2；C0 vs T2 作为支持性比较。
- 主要终点：同 checkpoint 内合法候选转换差；跨 case 先按 failure context 或 project 等权汇总。
- 次级终点：分层通过率、首次合法提交距离、请求/tokens/墙钟、无效或重复动作、删失和失败类型。

T1/T2 相对 C0 同时改变可操作诊断信息的内容和结构，不能解释成“纯 JSON 格式效应”。若要隔离格式，
C0 必须接收语义等价的非结构化内容；当前首选 estimand 是“合同派生反馈包的暴露效应”。详细设计
审计见 `docs/research/2026-09-29-contract-driven-repair-design-audit.md`。

研究负责人已于 2026-09-29 选择三臂。当前可执行性候选为 6 个项目、每项目 2 个 checkpoint、每 checkpoint
3 个反馈臂，共 36 arms；candidate delivery/target 与 build provenance 两个 stratum 分别报告。36 arms
不是统计功效结论，具体项目、checkpoint、顺序、多重比较规则和最小有意义效应仍需在预注册前冻结。

CXXCrafter-style、CompileAgent-style 或当前 Forge Multi-Agent 可以作为系统层相关基线或外部效度参照，
但不替代上述 matched-state 主比较。主问题研究的是候选合同反馈对失败恢复的作用，不是证明 Forge 整体
优于某一篇论文的实现。

## 8. 当前证据能支持与不能支持的结论

当前可以支持：

- Forge 已具备执行该研究所需的 checkpoint、候选合同、独立 evaluator、ledger 和 clean replay 基础；
- 两组探索性 `artifact_staging_missing` 结果的方向与主假设一致；
- `opaque_build_provenance` 已观察到 treatment conversion 和完整 replay，但确认性检验被 endpoint attrition
  阻断；
- Stage C v8 证明生产链路能在四个固定任务上完成端到端工程闭合。

当前不能支持：

- 结构化合同反馈对自然仓库失败存在总体因果效应或统计显著性；
- Forge 整体优于 CXXCrafter、CompileAgent 或其他系统；
- 某个 Provider 或模型普遍更适合自动化编译；
- verifier、matched-state、独立 authority 或分层评测是通用意义上的首次提出；
- 当前结果能外推到未观测项目、其他语言、其他环境或所有失败类型。

## 9. 设计审计结论与下一门禁

低成本、零 Provider 的实验设计审计已经完成。审计定义了主 estimand、合法转换判据、两个候选 fault
strata、原两臂建议、分析单位、删失和停止规则，并确认当前还不能冻结 Provider 实验。审计后研究负责人
进一步选择 C0/T1/T2 三臂，因此新 qualification 必须验证三种 feedback projection。详细入口：
`docs/research/2026-09-29-contract-driven-repair-design-audit.md`。

下一工程门禁应验证 Runtime v3 candidate submission 边界能在下一次模型调用前形成原子 checkpoint，并在
candidate delivery/target 与 build provenance 两个 fault strata 上证明 C0/T1/T2 除白名单 feedback
projection 外完全同源。门禁通过后，仍需由研究负责人选择最小有意义效应，并冻结具体项目/checkpoint、
顺序、多重比较规则、identity、预算与停止规则，才能请求新的实验授权。

## 10. 证据入口

仓库内：

- `benchmarks/reports/cpp-verifier-checkpoint-behavioral-pilot-v2.md`
- `benchmarks/preregistrations/cpp-verifier-multi-checkpoint-behavioral-pilot-v3.md`
- `benchmarks/preregistrations/cpp-opaque-provenance-confirmatory-replication-authorized.md`
- `benchmarks/reports/cpp-stage-c-v8-workspace-remediation-result-audit.md`
- `.claude/memory/project.md`

个人知识库原文：

- `01-研究/自动化编译/相关论文/2025-2026自动化编译论文索引.md`，标题“2025-2026 自动化编译论文索引”，
  SHA-256 `70ea8c9d25334f3a387d5094d78bab7544820daae3bfed3c1ddf7522ff5a2ba3`；
- `01-研究/自动化编译/相关论文/CXXCrafter-论文解读.md`，标题“CXXCrafter：论文解读与研究启发”；
- `01-研究/自动化编译/相关论文/CompileAgent-论文解读.md`，标题“CompileAgent：论文解读与研究启发”；
- `01-研究/自动化编译/2026-09-23-研究问题与小规模复现方案.md`，标题“Forge 自动化编译研究问题与
  小规模复现方案”，SHA-256 `c1765a008642d40f5f6c18e449ce62253e316729702076fe0491ccdad65cba6d`；
- `01-研究/自动化编译/Verifier-driven repair pilot失败分类与下一轮设计.md`；
- `01-研究/自动化编译/Opaque build provenance机制设计与reference criterion.md`。
