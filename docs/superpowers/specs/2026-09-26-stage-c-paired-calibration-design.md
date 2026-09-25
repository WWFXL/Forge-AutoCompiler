# Stage C 十二项目配对校准协议设计

日期：2026-09-26。追踪：Issue #310。前置决策：Phase 5 v5 decision 已记录 `phase5_complete=true`、`stage_c_authorized=true`、`stage_c_execution_started=false`。

## 目的与边界

Stage C 比较 CXXCrafter-style 固定 LLM Workflow 与 Forge Agent Workflow Node 在受控条件下的严格可复现构建成功率、成本和失败结构。Stage B 六项目已经暴露，只用于工程准入和合同校准，不进入 Stage C 分母。

本设计只冻结协议，不授权 Provider、Docker、正式 attempt、Stage C evidence 或模型 token。12 个 task、package snapshot、不可变镜像、controlled baseline adapter 和未授权 candidate runner 完成前，`stage_c_execution_started` 必须保持 false。

## 主要比较

主要 estimand 是受控系统比较：

- A：CXXCrafter-style controlled baseline，保留 Parser、Dockerfile Generator、Executor、LLM Judge 和 Modifier 循环。
- B：Stage B 已校准的 Deterministic Workflow + 单个有界 Build/Repair Agent Node。
- 两臂共享 exact source、target、不可变基础镜像、模型、请求政策、资源、网络、操作政策和 external evaluator。
- CXXCrafter 原生镜像选择和 Forge Lead + Compiler 多 Agent 不进入本轮主要比较；如需研究，必须使用独立协议和结果。

B 不启用新的零模型 fast path。Stage B 校准的是直接进入 Agent Node 的路径，在准入后增加 fast path 会改变方法身份。Submit 结构拒绝可在剩余全局预算内修正，每次拒绝和修正正常计入请求、步骤、工具和墙钟。External evaluator 在候选冻结后运行，失败结果不反馈给 Agent。

A 的内部 LLM Judge 只影响方法控制流，不能成为共同真值。最终候选必须转换为统一 candidate contract，并由与 B 相同的 evaluator 执行 S0-S5。

## Task 选择

冻结 12 个此前未由 A/B 运行的新 task：

- 4 个 CMake；
- 3 个 Make；
- 3 个 Autotools；
- 2 个其他或多构建系统项目；
- small、medium、large 尽量各 4 个；
- 覆盖文档明确、文档不完整和入口歧义。

选择过程必须结果盲：只读取预声明来源池、仓库元数据、exact-commit 源码、许可证、构建文件和文档，并执行零 Provider reference qualification。Stage B 六项目或已经查看过任一方法模型结果的项目不得进入主要 12 项。

每个分层内按 `sha256(selection_seed || repository_url || commit)` 排序并取满配额。候选全集、seed、排序键、排除原因和最终选择随 manifest 发布。Reference recipe 对两种方法隐藏，只供资格检查和 evaluator 使用。

每项冻结 repository URL、exact commit、submodule commit、source snapshot、build-system capabilities、分层 build system、target、artifact 集合、S3 oracle、bitwise 硬条件、操作政策和 qualification receipt。无法预先定义最低功能 oracle 的项目不得进入主要分母。

## 共享环境

- 使用同一个完整 image ID，不通过 tag 重新解析。
- 基础镜像绑定固定操作系统包仓库 snapshot；只有镜像固定而 package index 浮动时不得执行。
- 两臂使用相同 CPU、内存、磁盘、Docker daemon 和 `parallel_jobs=4`。
- dependency 阶段只允许白名单 package snapshot、task remote 和 exact submodule；configure、build、stage、oracle 和 replay 禁网。
- 禁止 `apt-get upgrade`、浮动 branch/tag、未固定下载和凭据持久化。
- 每个 arm 使用全新 Session、workspace、artifacts 和 replay，不共享可变缓存或构建树。

## 模型与预算

候选模型为当前已验证可达的 `deepseek-flash`；最终 execution amendment 冻结 Provider、endpoint、实际服务模型和服务支持的采样参数。请求 timeout 为 300 秒、Provider retry 为 0、禁止 fallback 和 parallel tool calls。凭据只检查环境变量存在性。

每个 arm 的候选上限沿用 Stage B：

- 300,000 recorded tokens；
- 24 model requests；
- 1,800 秒 method work deadline；
- 120 秒 cleanup reserve；
- 900 秒单命令 timeout；
- evaluator 和 clean replay 各 1,800 秒。

B 继续使用 64 agent steps、48 tool calls 和 32 commands。A 的 Generator、Judge、Modifier 请求全部计入共享请求、token 和墙钟上限；方法内部动作数只作描述指标，不强行映射为相同 tool call 数。

唯一 reachability 最多 1 request / 5,000 recorded tokens。48 arms 的机械 token ceiling 为 14,400,000，加 reachability 后为 14,405,000。正式 candidate 发布前必须用 Stage B 和既有 baseline 的只读成本分布做预算敏感性审计；该上限仍需单独执行授权。

## 配对调度

12 projects × 2 replicates × 2 arms，共 24 pairs / 48 physical attempts。

- Replicate 1 为 6 个 A->B、6 个 B->A。
- 每个项目的 replicate 2 使用相反 arm order。
- 项目顺序由冻结 seed 生成，不能按第一轮结果调整。
- 同一 pair 的 arms 相邻执行；两臂之间必须 cleanup 并验证 0 managed resources。
- 第一 arm 的普通失败不阻止第二 arm。只有 identity/evidence 损坏、cleanup/orphan 或资源安全问题关闭 batch。
- 禁止 retry、replacement、fallback、backfill 和 outcome 后重排。

预算只在完整 pair 前检查能否容纳下一 pair。已开始 pair 后尽量完成双臂；不完整 pair 保留在部署报告，不进入 paired estimate，也不得补跑。

## Outcome 与分析

主要终点为：

`strict_reproducible_build_success = S0 ∧ S1 ∧ S2 ∧ S3 ∧ S4 ∧ S5`

每个 replicate 的配对差为 `success_B - success_A`；每个 project 的 score 是两个 replicate 差的均值。Project 是独立分析单位，24 pairs 不能当成 24 个独立项目扩大样本量。

主要报告 12 个 project 的 A/B strict success、project-level paired delta、双成功/仅 A/仅 B/双失败四格、candidate generated/submitted 和 S0-S5 转化。区间使用 project-level 配对 bootstrap 或透明的 exact/randomization interval。Stage C 只校准方向和方差，不以 p 值或显著优越为主要结论。

次要报告 bitwise reproducibility、请求、tokens、费用、墙钟、无进展动作、Submit 拒绝/修正、源码或构建脚本修改、依赖与模块关闭，以及完整失败分类。等预算结果和方法实际消耗同时报告，不只报告成功样本成本。

## ITT、删失与停止

主要部署口径包含所有已登记 arm。模型行为失败、no-submit、预算耗尽、Provider request timeout、candidate verification 和 clean replay failure 均保留在分母。

只有在 pair 开始前的共享 preflight/reachability 失败、identity/evidence 无法可信分类、cleanup/orphan 破坏隔离，或宿主资源在 pair 前跌破门槛时，pair 才不进入 paired method estimate。单臂开始后的失败不静默删失。

以下情况立即关闭 batch：

- manifest、release、image、task、model 或 evaluator identity 漂移；
- hash chain、create-once 文件或终态不一致；
- 凭据泄漏；
- cleanup 失败或 managed orphan；
- 无法按合同收口的预算越界；
- oracle/adapter 共同缺陷使结果不可解释。

合法分类的 build failure、no-submit、graph/step/request/token exhaustion、candidate rejection、oracle/replay failure 和单次 Provider timeout 不关闭后续 batch，只要 evidence 与 cleanup 完整。协议缺陷必须保留旧 evidence 并派生新 identity，不得在原批次修复后重跑。

## Evidence

每个 arm 绑定 protocol/manifest/release/image/model、task/pair/replicate/arm/randomization、request ledger、命令与日志哈希、candidate/Submit、S0-S5、artifact/oracle/replay/bitwise、Session terminal state、cleanup 和 orphan audit。

最终报告分开提供 deployment ITT、paired method estimate、attrition/censoring、cost/reliability、bitwise、protocol deviations 和 evidence inventory/canonical SHA-256。

## 执行前硬门禁

1. 12 个新 task 尚未按结果盲规则冻结。
2. target、S3 oracle 和 bitwise 条件尚未完成资格审计。
3. package repository snapshot 和 Stage C image 尚未冻结。
4. CXXCrafter-style controlled adapter 尚未接入统一合同。
5. candidate manifest/schema/protocol/runner 尚未实现。
6. 14,405,000-token 最坏上限尚未获得执行授权。

任一条件未完成时都不得启动 Stage C。
