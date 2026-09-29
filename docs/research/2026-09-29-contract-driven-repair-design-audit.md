# 契约驱动自动化编译修复：零 Provider 实验设计审计

日期：2026-09-29
状态：设计审计完成，实验 identity 未冻结
工作类型：结果分析（只读源码、协议和历史证据；0 Provider、0 Docker、0 formal attempt）

## 1. 审计问题

本审计回答：Forge 现有机制和证据是否足以直接冻结一项“结构化候选合同反馈促进自动化编译修复”的
确认性实验；如果不足，最小缺口是什么。

审计读取了：

- 生产 `candidate_verifier.py` 与 Agent Workflow Runtime v3；
- `artifact_staging_missing` behavioral v2/v3 协议和结果；
- `opaque_build_provenance` independent replication 协议和冻结结果；
- Stage C v8 pre-freeze verifier canary 及结果审计；
- 相关零 Provider checkpoint、lifecycle、candidate、replay 和 cleanup 门禁。

## 2. 审计结论

**研究方向可行，但当前还不能冻结新的 Provider 实验。**

已有基础足以支撑新的零 Provider qualification：Forge 能冻结消息、环境和预算状态，已验证从同一 checkpoint
派生双臂，也能独立执行 candidate verification、functional oracle、provenance、clean replay 和 cleanup。
但历史实验使用了不同版本的故障定义和反馈合同，Runtime v3 的生产 pre-freeze 拒绝点尚未通过当前选择所需的
state-matched 三臂门禁。直接把历史结果或 runner 拼在一起，会混合 intervention、outcome 和 runtime 语义。

进入预注册前必须消除五个缺口：

1. **干预定义不统一。** Behavioral v2/v3 使用 `forge-verifier-repair-packet-1.0.0`，opaque provenance
   使用 `forge-opaque-provenance-repair-packet-1.0.0`，Runtime v3 直接返回
   `agent-workflow-prefreeze-response-v1` 的 `rejection_details`。
2. **生产拒绝点没有 checkpoint 证据。** Stage C v8 证明模型能在同一 attempt 根据
   `target_mapping_invalid` 修复，但没有从该拒绝状态派生 baseline/treatment，因此不是 treatment evidence。
3. **跨 fault-family 的目标总体未定义。** `artifact_staging_missing` 与 `opaque_build_provenance` 的历史
   case 不能自动视为同一可交换样本，必须预先定义分层和汇总权重。
4. **endpoint attrition 风险未解决。** Opaque replication 的 7/12 pair 删失使 4/6 project blocks
   不可估计；新的设计必须在 identity 中冻结 availability qualification、无响应重试语义和停止规则。
5. **历史 runner 不能作为当前执行基线。** 在当前树收集旧 opaque replication 测试时，冻结 runner 仍导入
   已从 `operations.py` 移除的 `resolve_command_role`，测试在 collection 阶段失败。冻结结果和历史 identity
   不受影响，但新 qualification 必须使用独立版本化 adapter，不能原地修补旧 runner。

### 2.1 审计后的研究负责人决策

2026-09-29，研究负责人在本审计的两臂建议基础上选择 **C0/T1/T2 三臂设计**：

- C0：普通候选失败；
- T1：错误分类与 code/path/expected/actual finding；
- T2：T1 + 不含命令、补丁或答案的抽象 repair goal；
- 主要比较：C0 vs T1；
- 次级比较：T1 vs T2；
- 支持性比较：C0 vs T2。

当前执行规模候选为 6 个项目 × 每项目 2 个 checkpoint × 3 个反馈臂，共 36 arms，两个 fault strata
分别报告。该规模尚不是功效结论；最小有意义效应暂未确定，具体项目/checkpoint、执行顺序和多重比较规则
仍需在预注册前冻结。下文 24 arms 保留为本审计当时的原始两臂建议，不再代表当前选择。

## 3. 建议的 estimand

### 3.1 干预

建议把 treatment 定义为：

> 在生产候选合同拒绝后，向 continuation 暴露一个由权威 verifier 确定性生成、字段白名单、有界且不包含
> 解法的 actionable feedback packet。

Baseline 接收同一个失败事件的普通失败载荷和相同剩余预算，但不接收上述 packet。两臂共享失败前的
消息、workspace、artifact、command history、容器镜像、预算和终止规则。

这个干预改变了**可操作诊断信息的暴露方式和内容**。除非未来 baseline 收到语义完全等价的非结构化文本，
否则不能把 estimand 表述为“纯结构化格式的作用”。论文应使用“合同派生反馈包的效果”，而不是“JSON
格式的效果”。

### 3.2 观测单位

- `checkpoint`：一个真实执行并提交后，被生产候选合同以单一预期分类拒绝、且可恢复的状态。
- `pair`：从同一 committed checkpoint 派生的一次 baseline arm 和一次 treatment arm。
- `project block`：同一个 `repository@exact_commit + target contract + fault stratum` 的两个独立 pair；
  两次 arm order 必须反转。
- 分析单位是 project block。两个重复用于降低模型随机性，不能当作两个独立项目扩大样本量。

### 3.3 主要终点

对 arm 定义二元结果 `strict_post_checkpoint_conversion`：

1. infrastructure identity、ledger 和预算有效；
2. continuation 在预算内提交候选，生产 pre-freeze verifier 接受；
3. 预声明 functional oracle 通过；
4. 独立 external evaluator 接受 artifact 与 provenance；
5. clean replay 通过；
6. finalize/cleanup 闭合且 0 managed orphan。

若任一项不满足，arm 不记为 strict conversion。模型达到 request/step/time limit、无 submit、候选再次被拒绝
都保留为 0 outcome。基础设施删失单独报告，不静默移出全部 schedule 分母。

Pair effect 为：

```text
delta_pair = Y_treatment - Y_baseline  ∈ {-1, 0, +1}
```

Project score 为两个 `delta_pair` 的均值。主要估计量是六个预先选择 project blocks 的等权平均差；它描述
这个固定研究样本，不自动代表全部 C/C++ 仓库。

## 4. Failure strata

建议首轮只纳入两个合同层，分别报告，不把所有 verifier code 平铺成同一种失败。

### A. Candidate delivery/target contract

候选来源是生产 `CandidateVerifier`。首轮优先使用能形成唯一、可恢复拒绝的：

- `target_mapping_invalid`；
- `undeclared_compiled_artifact`。

这两个 code 已有生产或历史观察：Stage C v8 的 `libjpeg-turbo` 观察到前者，Phase 5 v2 审计观察到后者。
正式 checkpoint 必须重新从结果盲态 fixture/case 构造，不能复制已观察模型答案或把历史 attempt 续跑。

暂不纳入：

- `delivery_unavailable`：通常意味着环境或挂载不可用，容易与基础设施故障混淆；
- `delivery_invalid` 和 `delivery_zero_byte`：适合零 Provider 负面对照，但真实样本定义尚不稳定；
- `functional_oracle_failed`：可能要求源码语义修复，和候选交付合同修复的动作空间不同；
- replay mismatch：发生在 candidate 冻结后，checkpoint 时点和 Runtime v3 pre-freeze 拒绝不同。

### B. Build provenance contract

使用 `opaque_build_provenance / build_system_unproven`，要求产物已存在、功能可验收，但可信构建调用链不足。
这一分类当前来自 experiment-only P2 reference criterion，不是生产 `CandidateVerifier` 的 finding；生产
`AgentWorkflowCandidateService` 只有较粗的 `build_system_mismatch` 检查。因此资格门禁还必须证明 P2
判定可以接到同一个 candidate submission/checkpoint 边界，而不改变双臂工具权限。修复必须通过真实
compiler tool surface，不能用直接写 command record 的测试捷径。

两层分别给出转换率和 project score。若最终需要一个总 estimand，六个 project blocks 等权；同时保留两个
stratum 的描述性结果，不根据观察结果改变权重。

## 5. 候选样本结构

建议规模为 **6 project blocks x 2 pairs x 2 arms = 24 arms**：

- candidate delivery/target contract：3 个项目；
- build provenance contract：3 个项目；
- 每个项目两个独立 checkpoint，arm order 分别为 `baseline -> treatment` 和
  `treatment -> baseline`；
- 在可行范围内覆盖 CMake、Make、Autotools，以及 executable/static/shared library；
- 项目必须在任何 Provider 请求前按 exact commit、目标、oracle、依赖和排除理由冻结。

选择六个 project blocks 是毕业论文可执行范围内的建议，不是统计功效结论。六个完整 project scores 可以
支持有限的配对随机化/符号翻转分析，但只有 treatment 方向高度一致时离散检验才有分辨率。无论 p 值如何，
结论都限于固定样本和冻结条件；每个 stratum 只有三个项目，只能做描述性解释。

当前**不冻结最小有意义效应**。建议在不读取新 outcome 的情况下，由研究负责人在预注册时从以下二者中
选择：

- 机制门槛：六个 project scores 的等权平均差至少 `+1/6`，且 treatment 不增加严格失败层级；
- 更强门槛：等权平均差至少 `+1/3`，与既有探索性效应量级相当。

这两个阈值是决策标准，不是从新样本估计出的统计功效。

## 6. Baseline/treatment 唯一差异

新的零 Provider gate 必须逐项证明：

| 对象 | 双臂要求 |
| --- | --- |
| source、commit、image、workspace、artifact | canonical digest 相同 |
| parent command/history、candidate request、rejection event | canonical digest 相同 |
| message checkpoint | 失败前历史相同；只允许 feedback exposure 字段不同 |
| budget | 初始 remaining request/turn/step/token/time 相同，后续独立计费 |
| tools 与 action policy | 完全相同，`parallel_tool_calls=false` |
| evaluator、oracle、replay、cleanup | 同一版本、同一规则，不接收 arm label |
| treatment packet | 只含白名单事实、抽象 repair goal 和有界路径，不含 shell、argv、patch、完整命令或答案 |

checkpoint 必须在 verifier 已产生 authoritative rejection、但该差异尚未进入下一次模型调用之前提交。
如果 Runtime v3 不能在这个时点原子捕获 message/environment/budget，设计保持阻断。

## 7. 次级指标

建议保留以下可机械复算指标：

- 到首次 accepted candidate 的 provider requests、model turns、graph steps、recorded tokens 和墙钟；
- submit 次数、pre-freeze rejection 次数及 code 序列；
- `policy_rejected` command 数；
- 相同 candidate contract SHA-256 的重复 submit 数；
- 各层通过率：candidate、functional oracle、provenance、clean replay、cleanup；
- endpoint、identity、evidence、Docker、oracle/evaluator 和模型行为终态。

“重复动作”只有在 action identity 与中间状态变化都能确定性定义后才能作为正式指标。当前可以稳定记录
重复 submit 和 policy rejection；不能仅凭自然语言轨迹主观标注模型“无效思考”。若要统计重复 shell 动作，
应先增加 `tool + role + workdir + canonical command SHA-256 + pre-action state digest` 的零 Provider 回归。

成本指标必须同时报告全 schedule 分母和 eligible arms。endpoint-censored arm 的已消耗请求、token 和墙钟
不能从成本中删除。

## 8. Endpoint、删失与停止规则

新 identity 必须独立于全部历史 experiment，并在预注册中选择一个实际可用的 provider/model。建议门禁：

1. 运行前冻结 endpoint、model、timeout、streaming、fallback 和 transport retry 规则；
2. 在 formal marker 前做零内容泄露的 availability qualification；qualification 失败则不创建 batch；
3. 若允许 transport retry，只能对“无响应、0 已记录输出、0 工具副作用”的请求使用，次数固定并计入请求
   和成本；不能重试模型行为失败或不满意答案；
4. arm 出现合法 endpoint censoring 时仍执行 cleanup，pair 标为不可估计，并继续或停止须由预注册规则决定；
5. 建议在前四个 formal arms 中出现两个 endpoint-censored arms 时停止整个 identity，避免再次形成高删失批次；
6. identity、checkpoint、evidence hash、budget、evaluator、cleanup 或 orphan 异常立即停止；禁止 replacement、
   backfill 和观察结果后的 schedule extension。

300 秒、0 retry 是历史 identity，不应自动继承为新论文实验的科学要求。新设计可以选择更可靠的 endpoint
或预注册有界 transport retry，但必须在任何正式 observation 前冻结。

## 9. CXXCrafter 与 Forge 架构比较的位置

主实验不需要复现 CXXCrafter 的 752 项结果，也不应把 CXXCrafter 当作唯一 baseline。主 baseline 是同一
Forge failure checkpoint 上未暴露合同反馈包的 continuation，因为它最直接识别候选方法的增量。

论文可以在相关工作和次级系统评测中比较：

- CXXCrafter-style 的 Dockerfile 整体修订；
- CompileAgent-style 的固定 Flow；
- Forge Agent Workflow Node；
- Forge Lead/Compiler Multi-Agent。

只有在四者能共享 exact commit、target contract、oracle、预算和外部 evaluator 时，才做定量系统比较。
否则只做方法结构与成功判据的定性对照。为完成毕业论文，不应让大规模复现阻塞主机制实验。

## 10. 零 Provider qualification 完成标准

下一工程步骤只实现实验资格门禁，不生成研究结果。完成标准是：

1. 至少一个 delivery/target case 经生产 `CandidateVerifier`、一个 provenance case 经 candidate submission
   加 P2 reference criterion，完成真实 Docker parent -> rejection -> checkpoint；
2. C0/T1/T2 state/budget/environment digest 相同，且 exposure diff 精确等于各臂允许的白名单 projection；
3. 确定性 scripted continuation 能分别消费三种 exposure，并闭合 production pre-freeze verifier、external
   evaluator、clean replay 和 cleanup；qualification 结果不作为反馈效果观测；
4. 包含错误 packet、跨 pair evidence、state drift、budget drift、evaluator 泄露和 orphan 的负面门禁；
5. 输出只包含合成 token/确定性模型计数，固定 `provider_calls=0`、`formal_attempts=0`、
   `experiment_evidence_writes=0`；
6. 不修改历史 manifest、runner、report 或冻结 evidence。

新 adapter 应读取历史报告作为只读设计依据，并绑定当前 Runtime v3/P2 组件的实际哈希；不得通过 monkey
patch 恢复已删除 API 来让旧实验 identity 在当前树重新可执行。

该门禁通过后才能建立候选 manifest、Schema、preregistration 和 plan-only runner。候选通过审阅仍不等于
授权；Provider、credential、formal attempt 和 evidence 写入必须由新的 authorized identity 单独开启。

## 11. 决策

本审计建议继续首选方向，并把下一项工作收敛为：

> **构建 Runtime v3 candidate submission boundary 的双 fault-stratum、state-matched、零 Provider qualification。**

该 qualification 按审计后的决策扩展为 C0/T1/T2 三臂；最小有意义效应继续保留为预注册前待决项。

暂不开展 CXXCrafter 复现、Multi-Agent 扩展或新的真实模型实验。若零 Provider gate 无法证明拒绝后、下一次
模型调用前的原子 checkpoint 和唯一 exposure diff，则应缩小主张为“分层候选验证系统设计与案例研究”，
不再宣称反馈干预效应。
