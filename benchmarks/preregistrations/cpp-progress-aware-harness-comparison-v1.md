# 进展感知结构化 Harness H0/H1 配对比较 v1 预注册

## 身份与授权

- Identity：`cpp-progress-aware-harness-comparison-v1`；
- Tracking Issue：[#433](https://github.com/WWFXL/Forge-AutoCompiler/issues/433)；
- Branch：`yiwei/433-h0-h1-provider-comparison`；
- Evidence root：`.compile-sessions/benchmark-evidence-progress-aware-harness-comparison-v1`，create-once；
- 工作类型：Q0 零 Provider 工程门禁、Q1 Provider canary、Q2 正式配对数据采集与结果分析。

用户已明确授权本阶段持续执行至关键结论，包括冻结身份后读取既有 `DEEPSEEK_API_KEY`、调用冻结 Provider、运行 Docker 和写入 formal evidence。Credential 值不得写入日志或 evidence。历史 identity/evidence 永久只读，禁止 replacement、backfill、同 arm retry 或结果后修改阈值。

## Treatment 与 estimand

H0 为 Runtime v3 原受限 ReAct Harness；H1 为 Runtime v4，增加权威进展快照、最近两次交互裁剪、candidate-ready guard 和 diagnostic guard。两臂共享模型、任务、checkpoint、工具、预算、离线 source archive、CandidateVerifier、functional oracle 和 S0-S5。

主要 estimand 是 9 个冻结 task、3 次独立 repetition 下，H1 相对 H0 的 strict success rate difference 与 Provider cost reduction。实验单位是一个独立 arm，配对单位是同 task、同 repetition 的 H0/H1 block，bootstrap 聚类单位是 task。

## 样本与顺序

Q0/Q2 使用 CMake、Make、Autotools 各 3 个 checkpoint，覆盖 state-1、state-2、state-3。Q2 为 27 pairs / 54 arms。奇数 block 顺序为 H0→H1，偶数 block 为 H1→H0；manifest 中的 block 顺序不可修改。

Q1 使用 `cmake-spdlog-state-2`、`make-libtommath-state-2`、`autotools-libestr-state-2`，共 3 pairs / 6 arms，不进入正式 estimate。

每个项目绑定 state-1 checkpoint 的同 commit workspace archive。H0/H1 clean replay 都必须从 archive 解包，禁止 `git fetch`。

## 模型、预算与停止规则

`deepseek-flash`，endpoint `https://api.deepseek.com`，thinking=false、streaming=false、retry=0。单臂最多 24 requests、300,000 recorded tokens、64 Agent steps、48 tool calls、32 commands和 1,800 秒。Q1+Q2 最多 1,440 requests、18,000,000 recorded tokens、`$21.60`。

Q0 必须 9/9 strict 且全部 offline replay/cleanup 闭合，否则 credential 读取和 Provider 阶段 fail closed。Q1 必须 6/6 分类终结并满足完整计量、身份绑定、动作后观察、cleanup 和无基础设施错误；strict success 不作为 canary 门槛。

Q2 已完成且分类的连续前缀可继续。任何 started marker 无 result、identity/release/component 漂移、预算上限突破、跨 arm 写入、cleanup 不闭合或 managed resource 残留都会关闭 identity。模型行为失败、no-submit、预算耗尽、Provider timeout、candidate/oracle/replay failure 作为结果保留，不停止后续 arm。

## 冻结分析

主要通过路径同时要求：

1. H1-H0 strict success difference 的 task-cluster 单侧 95% bootstrap 下界 `>= -0.10`；
2. H1 Provider cost 相对 H0 降低 `>= 20%`；
3. 三种构建系统中 H1 strict success 均不低于 H0。

替代路径同时要求：strict success 点估计提高 `>= 0.10`、bootstrap 下界 `> 0`、H1 cost 增加 `<= 10%`，并满足分系统不退化。Bootstrap 固定 10,000 次，seed=`43301`。

次要报告 recorded tokens、requests、wall clock、budget exhausted、no candidate、candidate submission、命令与 diagnostic、ready guard、上下文裁剪、首次 submit、recipe closure、S0-S5 和完整失败分类。次要指标不用于结果后更改主要决定。

## 解释边界

通过只支持当前受控 checkpoint、模型和预算下的自动化编译 Harness 领域方法与系统实证结论。失败不自动否定进展信息的全部用途，但会停止将 H1 整体作为主要机制。Jev、动态预算、自然失败、其他模型和通用 Agent Harness 均不在本 identity 中。
