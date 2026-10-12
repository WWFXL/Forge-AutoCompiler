# 固定 Agent continuation 资格 v2 预注册

## 身份与授权

- Identity：`cpp-agent-continuation-qualification-v2`；
- Tracking Issue：[#430](https://github.com/WWFXL/Forge-AutoCompiler/issues/430)；
- Parent evidence：`cpp-dynamic-budget-trajectory-benchmark-qualification-v5`；
- 工作类型：Q0 基础设施门禁、Q1 Provider canary、Q2 正式资格数据采集；
- Evidence root：`.compile-sessions/benchmark-evidence-agent-continuation-qualification-v2`，create-once；
- 用户已授权本阶段持续执行至关键结论，包括冻结身份后读取既有 Agent credential、调用冻结 Provider、Docker 执行和 formal evidence 写入。

历史 v1-v5 evidence 永久只读。禁止 replacement、backfill、同 arm retry 和结果后修改阈值。

v1 在首个 Q0 case 暴露了 Session 权威刷新缺失：reference 命令写入重新加载的 Session，CandidateVerifier 却接收旧内存对象，functional oracle 保存时覆盖命令历史。v2 只在 CandidateVerifier 前刷新权威 Session，并以独立 identity 从 Q0 重新开始；v1 不续跑、不修补。

## 样本

Q0/Q2 使用 9 个 checkpoint：

- CMake：`spdlog state-1`、`CLI11 state-2`、`cxxopts state-3`；
- Make：`libtommath state-1`、`tiny-AES-c state-2`、`kilo state-3`；
- Autotools：`libestr state-1`、`libfastjson state-2`、`libev state-3`。

Q1 使用不进入正式分析的 `spdlog state-2`、`libtommath state-2`、`libestr state-2`。

Q2 为 9 checkpoint x 3 repetitions = 27 arms。单一策略是固定 `escalate_agent` continuation；没有 direct、Jev 或 controller arm。

## 模型与预算

`deepseek-flash`，endpoint `https://api.deepseek.com`，credential env `DEEPSEEK_API_KEY`，thinking=false，streaming=false，retry=0。单臂最多 24 requests、300,000 recorded tokens、64 agent steps、48 tool calls、32 commands和 1,800 秒。Q1+Q2 总上限 720 requests、9,000,000 tokens。

Compile container 从 checkpoint 恢复后断开全部 Docker 网络；Provider 请求由宿主进程发起。Clean replay 仍按 Forge 严格终点从 exact commit 重建，但冻结 recipe 不允许把网络下载作为成功前提。

任一已开始 arm 不得重试。批进程只可在已完成且分类的连续前缀后继续；存在 started marker 但无 result 时，identity 失败封口。Provider 失败若缺少 token 证据，保持缺失并使成本完整性门禁失败。

## 门禁

Q0 必须 9/9 通过 CandidateVerifier、functional oracle、S0-S5、provenance、clean replay 和 cleanup。Q0 失败时不读取 credential、不创建模型、不执行 Q1/Q2。

Q1 必须 3/3 产生候选与 S0-S5 分类终态，token/预算完整、动作后观察与 cleanup 闭合。Q1 只决定工程链路是否可进入 Q2，不形成效果结论。

Q2 硬门禁和行为门槛以设计文档为准。全部通过时决定 `proceed_to_matched_outcome_matrix_design`，否则决定 `stop_before_dynamic_budget_controller_implementation`。

## 解释边界

Q2 估计的是固定 Agent 在冻结受控 checkpoint 上的 continuation 稳定性、成本完整性和恢复性。它不评价动态预算策略的优越性，不形成 direct/escalate/stop 反事实，不评价 Jev、自然失败或开放世界。

