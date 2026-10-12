# 进展感知结构化 Harness H0/H1 配对比较 v1 设计

## 研究问题

Issue #433 的 Runtime v4 零 Provider qualification v2 已证明进展快照、上下文裁剪、candidate-ready guard、diagnostic guard 和严格终点能够在真实 checkpoint 上闭合，但没有比较 Agent 效果。本实验回答：在模型、任务、checkpoint、预算、工具权限、离线源码和严格裁判完全一致时，H1 是否比 H0 减少无进展行为与 Provider 成本，同时保持或提高 strict success。

## Treatment

- H0：`AgentWorkflowRuntimeV3`。模型接收完整消息历史，候选就绪与诊断循环仅受 prompt 软约束。
- H1：`AgentWorkflowRuntimeV4`。每次请求前注入权威进展快照，只保留初始任务和最近两个完整交互；候选就绪时先要求 submit，连续 4 次无进展 diagnostic 后拒绝下一次 diagnostic；快照提供完整 replay command IDs、staged artifacts 和 target mapping。

两臂继续使用同一个 Compiler Agent system prompt、`run_container_bash`、`submit_candidate_v1`、CandidateVerifier、functional oracle、S0-S5、provenance 和 clean replay。H1 不自动生成命令、不自动接受候选，也不放宽终点。

## 样本与配对

正式样本继承动态预算轨迹 benchmark v5 的 9 个冻结 checkpoint：CMake、Make、Autotools 各 3 个，并分别覆盖 state-1、state-2、state-3。每个 checkpoint 做 3 个独立 pair；每个 pair 各运行一个 H0 和 H1 arm，共 27 pairs / 54 arms。

正式 block 顺序沿用父 manifest 的 27 项冻结顺序。奇数 block 先 H0 后 H1，偶数 block 先 H1 后 H0，形成不可结果后修改的交错顺序。每个 arm 使用独立 thread、Session、workspace、artifacts、candidate、evaluator 和 ledger。

Canary 使用 `spdlog state-2`、`libtommath state-2` 和 `libestr state-2`，同样各运行 H0/H1，共 3 pairs / 6 arms；canary 不进入 treatment estimate。

## 网络与源码身份

Compile container 从 checkpoint 恢复后断开网络。H0/H1 都绑定对应项目 state-1 checkpoint 的同 commit `workspace.tar.gz` 为 `repro/source.tar`，并核对 checkpoint SHA-256 和 archive SHA-256。Clean replay 必须通过 `source_snapshot`，生成脚本包含 archive 解包且不含 `git fetch`。这样网络路径不会成为两臂差异。

## 模型与预算

- 模型：`deepseek-flash`；thinking=false、streaming=false、retry=0；
- 单臂：24 requests、300,000 recorded tokens、64 Agent steps、48 tool calls、32 commands、1,800 秒；
- 60 个 Provider arms 的机械上限：1,440 requests、18,000,000 recorded tokens；
- 冻结价格：input `$0.30/M`、output `$1.20/M`；最坏费用上限 `$21.60`；
- Provider 超时、缺失 token、预算耗尽、no-submit、candidate rejection、oracle/replay failure 全部保留。

## 阶段门禁

### Q0：零 Provider reference closure

9/9 checkpoint 必须使用离线 source archive 通过 reference recipe、CandidateVerifier、functional oracle、S0-S5、bitwise reproduction 和 cleanup。失败则在 credential 读取前封口。

### Q1：配对 Provider canary

6/6 arms 必须分类终结、token/预算完整、parent checkpoint 与 source archive 绑定、动作后观察存在、cleanup 成功且没有基础设施错误。Strict success 不是 canary 门槛。

### Q2：正式配对实验

54/54 arms 必须分类终结并满足 token/预算、checkpoint、source archive、动作后观察、cleanup 和无跨 arm 写入门禁。Q2 可以从完整且分类的连续前缀继续；存在 started marker 但没有 result 的 arm 时禁止重试并封口。

## 指标与判定

主要指标是 H1-H0 strict success rate difference、按 task 聚类的单侧 95% bootstrap 下界，以及 Provider cost reduction。主要通过路径为：

1. strict success 差值的单侧 95% 下界不低于 `-0.10`；
2. H1 总 Provider cost 相对 H0 至少降低 20%；
3. CMake、Make、Autotools 中 H1 strict success 均不低于 H0。

替代通过路径要求 strict success 点估计至少提高 0.10、bootstrap 下界大于 0，且 H1 cost 增加不超过 10%，同时满足分系统不退化。

次要指标包括 recorded tokens、requests、wall-clock RMST、budget exhausted、no candidate、candidate-ready 后请求/工具/命令、连续 diagnostic、首次 submit 延迟、submit rejection/resubmit、recipe closure 和失败分类。所有成本均按全体已登记 arms 报告，不只报告成功案例。

H1 若只减少消息长度而不满足任一联合通过路径，只定位为工程优化。收益若来自 verifier 放宽、只出现在单一构建系统、增加错误提交或 evidence/cleanup 不完整，则停止把 H1 作为主要研究机制。

## 解释边界

本实验只评价冻结受控 checkpoint、`deepseek-flash` 和固定预算下的 Harness 整体处理效应。它不评价 Jev、动态预算、自然失败、开放世界、其他模型或 Claude Code/Codex。通过后先做有限组件消融，再决定是否构造动态预算 direct/continue/stop outcome matrix。
