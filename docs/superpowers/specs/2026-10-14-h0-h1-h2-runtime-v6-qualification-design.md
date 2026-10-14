# Runtime v6 的 H0/H1/H2 held-out 正式比较资格设计

> 日期：2026-10-14
> Tracking Issue：[#451](https://github.com/WWFXL/Forge-AutoCompiler/issues/451)
> 工作类型：实验设计与零 Provider 基础设施资格

## 1. 研究问题

Issue #447 的三臂 canary 暴露了 Runtime v5 在 replay closure 拒绝后的恢复死锁，Issue #449 已用 Runtime v6 完成
有界恢复工程门禁。因为 Runtime v6 是观察 `mjson/H2` 后开发的，旧 `tinyxml2/mjson/libcsv` observation 不能进入新的
无偏效果分母。

本阶段只为后续正式比较建立 held-out 样本和可执行合同。后续正式问题是：Runtime v6 的 pre-freeze replay closure 与
有界 submit-rejection recovery，能否相对 H1 保持严格成功非劣，并减少不可复现 candidate，而不产生不可接受的
Provider 和墙钟开销。

三臂固定为：

- H0：Runtime v3，带 CandidateVerifier 的原始受限 ReAct；
- H1：Runtime v4，在 H0 上增加权威进展快照、上下文裁剪与行为门禁；
- H2：Runtime v6，在 H1 上增加 replay closure，以及仅针对非终态 `recipe_execution_failed` 的一个 build 加一个
  artifact-stage 有界恢复窗口。

H1 必须保留，以识别 replay closure/recovery 相对结构化 Harness 的增量。

## 2. 样本与筛查纪律

先对整个仓库的既有 benchmark、report 和研究文档做项目族精确搜索，再进行只读构建入口检查。结果后不得在当前
identity 内替换项目。

| 构建系统 | 项目 | exact commit | 冻结目标 |
| --- | --- | --- | --- |
| CMake | `commonmark/cmark` | `7e1e10c32ca1275e387057606752123efc3e2793` | `lib/libcmark.a` |
| Make | `orangeduck/mpc` | `1049534fc56b1971345c7aaa792dea55d6f9b7bc` | `lib/libmpc.a` |
| Autotools | `libexpat/libexpat` | `ac140c2d34e0aafb1c6a126ca2917ff32d765518` | `lib/libexpat.a` |

三者在冻结前均未出现在 Forge 版本化研究资产中。`benhoyt/inih` 因没有根 CMake 入口在 source-only 阶段排除；
`zserge/jsmn` 的主要产物为 header-only，不满足本比较要求的真实编译库终点，因此在 source-only 阶段排除。构建结果
不会用于在同一 identity 内继续挑选候选。

## 3. 共同预算与正式 estimand

后续 18-arm 正式比较使用每项目每臂两次重复。三臂共享：

- 下一请求停止阈值 `600,000` recorded tokens；
- 单响应上界 `100,000`，单臂授权上界 `700,000` recorded tokens；
- 最多 36 次请求、96 Agent steps、72 次工具调用和 48 条命令；
- node、evaluator、replay 各 1800 秒，单命令 900 秒，cleanup 120 秒；
- 相同模型、source archive、compile image、并行度、functional oracle 和 external evaluator。

主要 estimand 为项目族聚类的 `strict_success(H2) - strict_success(H1)`，非劣界为 `-0.10`。主要机制指标为
pre-freeze closure rejection、repair window 开放/消费、二次 submit、external replay failure 和错误冻结。H1 相对 H0 的
Provider requests、recorded tokens 与成本只作为结构化 Harness 消融；H2 相对 H0 为完整系统比较。

三个项目族只能支持有边界的机制复现，不能据此主张开放世界或广泛项目总体泛化。

## 4. 零 Provider 资格

Identity 为 `cpp-progress-aware-h0-h1-h2-runtime-v6-qualification-v1`。

- Q0：重新 clone exact commit，以 `git archive --format=tar HEAD | gzip -n` 生成确定性 source archive，并核对
  SHA-256 和大小。
- Q1：在固定 gcc13 镜像、禁网容器中执行 reference recipe、functional smoke 和 artifact stage，再调用真实
  `ReplayClosureVerifier`。要求 delivery 路径、类型、大小与 SHA-256 一致。
- 绑定门禁：H0/H1/H2 必须精确映射 Runtime v3/v4/v6；H2 的 v6 组件哈希必须冻结。
- 生命周期门禁：Session 保持活动、正式 replay attempt 为 0、全部容器清理、credential/Provider/Jev/model token/
  formal effect attempt 均为 0。

全部通过后，决定为 `proceed_to_runtime_v6_three_arm_formal_comparison_design`；任一门禁失败则为
`stop_before_runtime_v6_three_arm_formal_comparison`。资格数字不构成 treatment effect。

## 5. 权限与停止规则

本 identity 允许公开源码网络、Docker、新 create-once evidence 和版本化报告。禁止读取 credential、调用 Provider/Jev、
执行正式效果 arm、replacement、backfill、修改历史 evidence 或实现动态预算 controller。正式 Provider 比较必须另建
identity，并在读取 credential 前冻结 release、执行顺序、总预算、停止规则和报告方法。
