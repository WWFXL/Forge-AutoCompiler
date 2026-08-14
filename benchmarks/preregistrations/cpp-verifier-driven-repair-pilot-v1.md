# Forge C/C++ verifier-driven repair pilot 决策包

> 状态：设计完成，运行时实现与模型采集均未授权。跟踪 Issue：#123。

## 研究问题

在模型、项目、容器、调用次数、token 和墙钟预算都相同的条件下，向 Compiler 返回确定性的结构化 verifier repair packet，能否提高 C/C++ 自动编译的 Oracle 与端到端成功率？

首批 12 槽只是可行性 pilot。它验证 treatment 是否真的只改变反馈、证据是否闭合、成本是否可承受，不做显著性检验、模型排名或总体效果声明。

## 为什么不是“有 verifier / 无 verifier”

当前 baseline 已经具备强制 artifact 检查和 clean replay，Compiler prompt 也要求 `submit_build_result` 失败后继续修复。现有失败返回包含状态、attempt/command ID、镜像、候选 artifact 元数据和首条错误 `message`，并非“没有反馈”；但它没有把 evidence 中的 primary classification、failed checks、build-system identity 或 artifact diff 规范化返回给 Compiler。

因此 treatment 的唯一变化是：在可修复的 verification-domain submit 失败后，把 verifier 已有的白名单结构化事实作为 `repair_packet` 附加到同一次工具返回。它不增加调用次数、turn、timeout 或 token 预算，也不改变 Oracle、clean replay 或 delivery gate。

## 既有证据信号

- formal v4 的 DeepSeek `cppitertools` rep-001 先后出现 `candidate_verification_failed` 和 `build_system_unproven`，第三次 submit 与 clean replay 通过。这证明现有 Agent 能自然修复，但不是 treatment 效果证据。
- formal v4 的 RichLab rep-002 在 `recipe_execution_failed` 后连续遇到 endpoint timeout，最终失败；该轨迹被网络事件混杂，不能作为 repair treatment 的负例。
- formal v3 的 `open62541` 和 pilot v8 的 `hiredis`、`libcheck`、`sysstat` 还观察到 size、SHA-256、build-system 与候选验证失败，说明 verifier failure taxonomy 不只存在于单一项目。
- 所有历史 ledger/report 保持冻结，本决策包只引用路径、SHA-256、physical attempt ID 和白名单事件。

## Treatment

| Arm | 行为 |
|---|---|
| Baseline | 保持 `main@6eb69e64` 的失败 payload 和 Compiler prompt 不变。 |
| Repair packet | 在同一失败 payload 中增加固定 schema 的 `repair_packet`。 |

packet 只允许以下内容：failure domain、primary classification、failed checks、build-system identity、artifact identity diff、replay status、固定 repair goal，以及 submit/replay/supporting-command ID。禁止 stdout/stderr、prompt、模型正文、密钥、宿主路径和生成式修复命令。

以下 verification classification 可激活 treatment：候选验证失败、build-system selection/unproven/mismatch、recipe execution、artifact set/type/size/SHA-256 和 smoke mismatch。

模型 endpoint、provider 连接、attempt/Compiler 预算、daemon/preflight、cleanup/finalization 失败不属于 treatment 可修复事件，必须单列，不能算成 repair 失败。

## Case 选择

选择规则在结果之外固定：按 formal-v1 case protocol 的原始顺序，在 Autotools、CMake、Make 三个 stratum 中分别选择第一个从未进入 formal v3/v4 physical attempt 的项目。只依据 prior exposure，不依据历史成功或失败。

| Case | Build system | Exact commit | Oracle artifact |
|---|---|---|---|
| `liblouis` | Autotools | `b52ab11ade4cf0917315991b54a8558a2589cf55` | `liblouis.a` |
| `openthread` | CMake | `044aa98f1b5255731e0a6f2816e267b282299684` | `libopenthread-ftd.a` |
| `mupdf` | Make | `b29caae1ab8c602187d4fc36d7b540bac493635d` | `libmupdf.a` |

## Pilot 规模

设计为 `3 cases × 2 providers × 2 treatment arms × 1 repetition = 12 slots`，形成 6 个完整 pair。每个 pair 的 treatment 顺序交叉平衡，防止所有 baseline 或 treatment 总在更早的网络时段运行。

- RichLab：`gpt-5.5`
- DeepSeek：`deepseek-v4-flash`
- request timeout：300 秒
- provider retry：0
- physical-attempt 总墙钟：1,800 秒
- 每 attempt 最多 2 次 Compiler invocation、48 次模型请求、36 turns
- 建议 expected recorded tokens：800,000
- 建议 maximum recorded tokens：2,400,000

预算只在完整 pair 前检查。若只完成一个 arm，已有 attempt 保留为描述性证据，但该 pair 不进入 paired pilot 结果。禁止 retry、replacement、fallback 和 backfill。

## 指标与判定

主要指标为 `oracle_passed`。次要指标包括：端到端 terminal pass、首次 actionable verifier failure 后的修复转化、false acceptance、submit/replay 次数、模型请求、tokens、墙钟和 failure transition。

pilot 只报告 6 个 pair 的一致/不一致结果与成本，不计算 p-value。只有 treatment fidelity、evidence、预算和运行稳定性都通过，下一阶段才设计至少 3 次重复的正式实验。

## 有效性边界

- 两个 arm 使用相同 prompt、模型、case、commit、镜像、网络与预算；Memory 和 Skill 均关闭。
- 每个 attempt 使用全新 Compile Session 和 clean replay，不共享 workspace 或 artifacts。
- packet 本身会增加少量输入 token，必须单独计量，不能隐藏在成功率中。
- 模型随机性无法由单次 repetition 消除，因此 pilot 不估计正式效应大小。
- runtime adapter、Schema、runner、canary 和 analyzer 必须在任何模型请求前另行实现和冻结。
- 本文件和 JSON 均不授权模型调用。真实实现与采集必须另开中文 Issue/PR，并由实验负责人确认槽位和 token ceiling。

## 方法来源

- [CXXCrafter](https://github.com/seclab-fudan/CXXCrafter-Community-Edition)：C/C++ 构建脚本生成与执行-反馈-修复闭环。
- [Self-Refine](https://arxiv.org/abs/2303.17651)：反馈与迭代改进范式。
- [CRITIC](https://arxiv.org/abs/2305.11738)：外部工具反馈驱动的自我校正。
- [SWE-agent](https://arxiv.org/abs/2405.15793)：真实软件环境中的 Agent-Computer Interface。
- [RepairAgent](https://arxiv.org/abs/2403.17134)：测试失败驱动的自主修复循环。

机器可读来源为 `cpp-verifier-driven-repair-pilot-v1.json`。若 Markdown 与 JSON 冲突，以 JSON 为准。
