# 主动诊断动作价值候选机制审计

> 日期：2026-10-09
> Tracking Issue：[#385](https://github.com/WWFXL/Forge-AutoCompiler/issues/385)
> 工作类型：结果分析、文献研究与零 Provider 资产审计
> 文献截止：2026-10-09
> 权限边界：未调用 Provider、未读取 credential、未创建 formal identity 或 formal attempt，未写入或修改任何冻结
> experiment evidence。

## 1. 结论

**停止“主动诊断动作价值”作为 Forge 的新机制候选，不进入预注册、controller 或 Provider 实验。**

候选原本希望联合四个要素：维护竞争性失败原因假设、为诊断动作定义成本和可能证据结果、按预期假设排除价值
选择下一动作、在证据充分时修复或停止。审计发现，这四个要素已被既有工作分别或联合直接覆盖：

- `LLM-as-an-Investigator` 已维护竞争假设、生成区分性问题、逐轮更新假设概率，并按置信阈值或问题预算停止；
- 2024 年 cost-aware active testing 已统一观察、主动测试、系统干预和组件替换，并用反事实决策支持选择下一诊断步骤，
  目标是最小化期望总诊断成本；
- `Calibrate-Then-Act` 已把带成本的信息采集形式化为 POMDP，在编程任务中根据潜在环境状态、先验、观察与动作成本
  选择测试、执行或提交；
- 信息增益驱动的测试选择和 Bayesian experimental design 也已有直接先例；最近的 LLM Agent 工作还分别覆盖了
  信息增益澄清、成本约束工具获取、交互式 debugger 和显式 repair hypothesis。

因此，把这些机制迁移到 CMake、Make 和 Autotools，剩余增量是公共根因/探针 schema、构建系统 adapter、严格执行
oracle 和新 benchmark。这可以形成有价值的**应用或评测贡献**，但不是本项目要求的独立研究机制。

Forge 现有资产也不能直接支持可信的最小动作价值实验。阶段 0 的 30 条 session 只观察每个状态下实际选择的一个动作，
没有同一快照上的替代诊断结果；264 个 diagnostic 记录包含 256 条不同 Shell 命令，且输入清单没有独立根因标签。
从这些轨迹回顾性估计信息价值会把 Agent 原策略、项目差异和动作结果混在一起。

两个放弃条件已经同时触发：核心机制被直接先例覆盖，现有资产缺少反事实动作结果。继续实现只能证明 Forge 可以复现
主动诊断范式，不能证明新增机制。

## 2. 审计对象与判定标准

### 2.1 候选机制

候选状态和动作原本可写为：

```text
H_t = {h_1: p_1, ..., h_n: p_n}
A_t = {a_j: (cost_j, possible_evidence_j)}
a_t = argmax_a expected_hypothesis_reduction(a | H_t) / cost(a)
```

其中 `H_t` 是竞争性失败原因及其当前权重，`A_t` 是可执行诊断动作。动作结果更新 `H_t`；当某个假设达到证据门槛，
或继续诊断的期望价值低于成本时，系统进入修复、升级、放弃或停止。

它要解决的真实问题是：相同的高层错误类别可能对应多个根因，固定诊断序列会执行无关检查，自由 Agent 又可能过早
修复或重复检查。研究问题本身成立，但问题重要不等于机制新颖。

### 2.2 通过条件

本候选只有同时满足以下条件才可进入最小实验：

1. 竞争假设、证据动作、成本和停止的联合决策相对 2024-2026 工作有可指出的机制差异；
2. 差异不是换成 C/C++ 或三个构建系统，也不是把已有方法串接起来；
3. Forge 资产包含独立根因、候选动作、每个动作的可执行结果和成本，或能以低成本冻结新的无泄漏 fixture；
4. 最小实验能只改变动作选择机制，并观察正确诊断、动作充分性和总诊断成本；
5. 失败条件在查看结果前可冻结。

第 1、2 和 3 项未通过，因此没有创建实验 identity，也没有结果后补定指标或阈值。

## 3. 2024-2026 直接先例

### 3.1 机制覆盖矩阵

| 候选要素 | 直接先例 | 已覆盖的机制 | 对本候选的影响 |
| --- | --- | --- | --- |
| 竞争假设与概率更新 | [LLM-as-an-Investigator](https://arxiv.org/abs/2606.13220v1)，§4 | 显式候选解集合、归一化概率、逐答案更新、置信阈值和问题预算 | “维护多个失败假设后再决策”不能作为新增机制 |
| 区分性诊断动作 | [LLM-as-an-Investigator](https://arxiv.org/abs/2606.13220v1)，§4.3 | 针对最具竞争性的假设生成区分问题，避免重复问题 | 换成 Shell 探针只改变动作载体 |
| 成本约束主动测试 | [Efficient Differential Diagnosis using Cost-aware Active Testing](https://doi.org/10.36001/ijphm.2024.v15i3.3849) | 统一观察、主动测试、干预和替换；用因果/反事实决策支持选择下一步并最小化期望总成本 | 已直接覆盖“动作成本 + 证据价值 + 下一步诊断” |
| 潜在状态、观察与探索/提交 | [Calibrate-Then-Act](https://arxiv.org/abs/2602.16699v3)，§2-4 | POMDP、潜在环境状态、先验/后验、多种探索动作、动作成本和 commit；包含文件读取编程任务 | 跨构建系统只是在新的环境中实例化同一决策结构 |
| 最大信息量测试 | [Efficient Test Selection in Active Diagnosis via Entropy Approximation](https://arxiv.org/abs/1207.1418v1) | 在诊断假设上按条件熵近似选择下一项最有信息量的测试 | 简单 entropy/information-gain 选择已有成熟先例 |
| 信息增益策略学习 | [Uncertainty-Aware Clarification in LLM Agents with Information Gain](https://arxiv.org/abs/2606.03135v1)，§3.3 | Bayesian experimental design、EIG、belief-update reward 和策略优化 | 用 LLM 生成高信息量探针也不是独立机制 |
| 成本约束工具获取/停止 | [Scores Are Not Decisions](https://arxiv.org/abs/2607.27083v1) | 以 downstream payoff 和异质工具成本学习 stop/continue，证明 score-only 规则不足 | “工具相关度阈值 + 成本”已不足以构成创新 |
| 可执行运行时诊断 | [Debug2Fix](https://arxiv.org/abs/2602.18571v2) | debugger subagent 通过 breakpoint、step 和变量检查回答根因问题 | “让 Agent 主动执行诊断工具”已有软件工程直接先例 |
| 显式修复假设与动态证据 | [PracRepair](https://arxiv.org/abs/2606.17612v1) | question-driven failure diagnosis、显式 repair hypothesis、failure execution 和 validation dynamics | “先诊断再修复”在 APR 中已有直接实现 |

`CompileAgent` 还已在固定编译 Flow 内让 MasterAgent 动态选择网站搜索或多 Agent 错误讨论；`EvoConfig` 已包含专家诊断、
多 Agent 自反馈和修复优先级；`GradleFixer` 已把领域工具接入受限动作空间；`EnConda-Bench` 已分开评价错误识别、
描述、修复建议和最终执行。它们不单独实现成本归一的信息增益，但与上表工作组合后，已覆盖本候选的各个组成部分。

### 3.2 相对最新论文新增了什么

本次没有找到足以保留为主要创新的新增决策机制。剩余可实现内容是：

1. 定义跨 CMake、Make、Autotools 的公共失败假设和诊断探针；
2. 把 Shell 观测映射为带 provenance 的证据；
3. 记录诊断动作的时间、风险和副作用；
4. 用严格构建合同和 clean replay 评价最终修复。

这些内容能提高复现性和构建领域覆盖，但没有改变已有的 hypothesis update、active test selection、EIG、POMDP 或
cost-aware stopping。它们属于领域建模、系统实现和评测协议。

### 3.3 是否只是场景迁移或工程组合

是。最直接的实现会把 `LLM-as-an-Investigator` 的问题替换为构建探针，把 `Calibrate-Then-Act` 或 active testing 的
成本效用规则用于选探针，再复用 Forge 的 Session、verifier 和 replay。该组合有工程价值，但其因果图和决策规则
没有新的变量、约束或学习目标。

构建动作可能改变 workspace，确实比纯问答更复杂；但 POMDP 和 2024 cost-aware active testing 已允许状态转移、
系统干预和组件替换。仅增加 `side_effect` 标记不能建立新的机制主张。

## 4. Forge 资产资格审计

本节是阶段 0 完成后的独立、只读、后验资产审计。它不修改
`cpp-cross-build-progress-state-qualification-v1` 的输入、结果或结论，也不把新读取的命令文本用于挽救 v1。

### 4.1 可用资产

- 固定 manifest 包含 30 条 session，覆盖 18 个项目族；开发集 6 条 session/100 个决策点，测试集 24 条
  session/309 个决策点；
- 409 个 eligible commands 中有 264 个 `diagnostic`、39 个 `artifact_stage`、34 个 `smoke`、34 个 `build`、
  29 个 `configure` 和 9 个 `dependency`；
- diagnostic 动作中 223 个 `exit_code=0`，32 个执行后非零退出，9 个被 policy 拒绝；
- Session 记录了实际命令、开始/完成时间、退出码和日志，Forge 也具备独立容器、固定 commit、严格 evaluator、
  functional oracle、provenance 和 clean replay；
- Stage C v6 另有 4 条后验 strict failure 根因审计，可用于说明 delivery 缺陷，但不是诊断动作比较数据。

这些资产足以重放实际轨迹、核对单个探针返回了什么，并为未来受控 fixture 提供执行基础。

### 4.2 不能支持动作价值估计的缺口

1. **没有反事实动作结果。** 每个 workspace 状态只沿原 Agent 选择的一个动作继续，没有从相同快照执行候选探针集合。
2. **没有独立根因标签。** 阶段 0 manifest 的 30 条输入记录均没有 `root_cause`、`fault`、`diagnosis` 或
   `ground_truth` 字段；任务合同定义目标产物，不定义当时 Agent 正在区分的唯一失败原因。
3. **动作空间未冻结。** 264 个 diagnostic 记录包含 256 条逐字不同的 Shell 命令，不能直接形成具有共同前置条件、
   观察空间和成本的动作类型。
4. **动作由旧策略选择。** 成功轨迹中的检查顺序同时受项目、模型上下文和此前观察影响；直接比较后续成功会有严重
   selection bias。
5. **成本只有 realized value。** `duration_seconds` 和模型 token 能描述实际轨迹成本，不能提供未执行动作的期望成本
   或失败风险。
6. **四条 root-cause 审计不构成分支实验。** 它们是候选冻结后的 delivery 失败，只有后验根因，没有同一失败状态的
   多个诊断动作结果。

因此，旧轨迹不能用于训练或评价一个可信的 EIG policy。要完成实验，必须新建受控故障、可恢复快照和全动作 outcome
matrix；这已经是新的数据集建设，而不是对现有证据的低成本资格审计。

## 5. 最小可证伪实验

如果未来把目标改为“构建领域主动诊断 benchmark 或应用效果”，最小实验应采用新的零 Provider identity，而不是复用
旧轨迹：

1. 在 CMake、Make、Autotools 各选择至少 4 个项目族；同一高层症状下设置至少两个不同根因，避免错误类别直接泄漏答案；
2. 每个 case 冻结 clean snapshot、唯一根因、3-6 个无答案泄漏的 typed diagnostic actions、动作成本和允许副作用；
3. 从独立恢复的相同 snapshot 执行每个动作，冻结完整 outcome matrix，训练/开发和未见项目族测试严格隔离；
4. 比较固定序列、错误类别规则、仅维护假设但不计成本、cost-normalized information gain 四种策略；
5. 主要指标为达到正确根因或安全 abstain 所需的总诊断成本；同时报告 top-1 根因准确率、无效探针数、错误修复率，
   以及冻结的一次修复后 strict acceptance；
6. 只有在未见项目族上以不降低根因准确率为前提稳定降低成本，并在去掉 hypothesis update 或 cost normalization 后
   收益消失，才能说明该实现有效。

该实验能证伪“主动诊断在构建领域有应用价值”，但即使通过，也不能自动把已有主动诊断算法变成新的通用机制。
本阶段因文献资格已失败，不冻结样本量、最小效应或统计门槛，也不执行此实验。

## 6. 放弃条件与最终决定

| 放弃条件 | 观察 | 状态 |
| --- | --- | --- |
| 核心机制被直接先例覆盖 | 竞争假设、区分问题、概率更新、EIG、成本动作选择和停止均有直接先例 | **触发** |
| 剩余差异只是构建场景或工程组合 | 新增内容主要是 build-system schema、adapter、oracle 和 benchmark | **触发** |
| Forge 现有资产不能识别动作价值 | 无同快照替代动作结果、无独立根因，diagnostic 命令几乎逐条唯一 | **触发** |
| 最小实验不优于固定序列/错误规则 | 未进入实验 | 未检验 |
| 收益依赖项目身份、答案泄漏或单一构建系统 | 未进入实验 | 未检验 |

最终决定为 `abandon_active_diagnosis_as_novel_mechanism`。Issue #385 不创建 formal experiment identity，不实现
controller，不调用 Provider，也不把旧轨迹改造成伪 counterfactual 数据。

这不否定主动诊断作为产品能力或 benchmark 主题的价值。若后续选择这条路线，论文贡献应明确改为“跨构建系统主动诊断
benchmark、可执行探针协议或应用实证”，不能继续表述为新的 hypothesis/EIG 控制机制。

## 7. 证据与引用边界

### 7.1 仓库证据

- 阶段 0 manifest：`benchmarks/manifests/cpp-cross-build-progress-state-qualification-v1.json`；
- 阶段 0 报告：`benchmarks/reports/cpp-cross-build-progress-state-qualification-v1.json`；
- 阶段 0 extractor：`scripts/forge_progress_state_qualification.py`；
- 四条 strict failure 审计：`benchmarks/reports/cpp-stage-c-v6-failure-audit.md`。

### 7.2 知识库证据

本轮按 `search_notes -> read_note` 读取：

- `01-研究/自动化编译/相关论文/2025-2026自动化编译论文索引.md`，标题“2025-2026 自动化编译论文索引”；
- `01-研究/自动化编译/相关论文/CompileAgent-论文解读.md`，标题“CompileAgent：论文解读与研究启发”；
- `01-研究/自动化编译/相关论文/EnConda-Bench-论文解读.md`，标题“EnConda-Bench：过程级轨迹评价论文解读”；
- `01-研究/自动化编译/相关论文/SWE-Agent测试时计算与早停论文对比.md`，标题“SWE Agent 测试时计算、轨迹复用与早停论文对比”。

知识库用于核对既有研究边界，未修改。EvoConfig 和 GradleFixer 在知识库索引中为待导入状态，本报告对它们只采用
公开论文索引和原始公开来源，不把索引摘要扩展成未核对的方法细节。

### 7.3 能够与不能够得出的结论

能够支持：

- 本次定向检索语料中，候选的核心机制已有直接覆盖；
- Forge 阶段 0 固定轨迹缺少估计替代诊断动作价值所需的数据结构；
- 当前候选不应进入 controller 或 Provider 实验。

不能支持：

- 主动诊断对自动化构建没有产品价值；
- 世界范围不存在任何更窄的构建诊断机制空白；
- 任一未执行动作的反事实效果；
- Forge、模型或策略的总体优劣；
- 新 benchmark 的预期效果、统计显著性或成本节省比例。

本次是定向机制审计，不是系统综述，不能声称全球首次或完备排除所有相关工作。
