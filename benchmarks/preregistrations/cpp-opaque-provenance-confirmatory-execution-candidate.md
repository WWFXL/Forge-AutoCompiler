# Forge opaque provenance 六 case confirmatory execution candidate

- GitHub Issue：[Issue #235](https://github.com/WWFXL/Forge-AutoCompiler/issues/235)
- 父协议：Issue #233 candidate v2
- 状态：pre-execution、未授权、零 provider

## 目的

在任何模型请求前冻结确认性批次的 provider identity、evidence identity、case dispatch、终态分类与批次停止规则。本候选只证明既有 lifecycle、runtime parity、R0、agent construction 和批次状态机可以组合；不实现或暴露真实采集入口。

## 冻结执行身份

- Provider/model：DeepSeek `deepseek-v4-flash`，endpoint `https://api.deepseek.com`，credential 仅以环境变量名 `DEEPSEEK_API_KEY` 标识。
- 每请求 300 秒、0 retry、非 streaming、禁止 fallback、replacement 与 backfill。
- 六 case、12 pairs / 24 arms、项目内 arm order 对调、4/2/2/2 action limits、每 arm 120,000 与批次 2,940,000 recorded-token ceiling 全部继承父协议。
- Evidence 使用新的只写一次目录；reachability、batch、pair、arm、checkpoint 与 cleanup identity 不复用任何历史实验。

选择 DeepSeek 是为了保持三个有效 exploratory pair 的 provider/model 条件，不把模型切换混入确认性 treatment effect；这不是模型排名，也不授权调用。

## 复用边界

- 六 case 的 bootstrap、parent fault、P2 conversion、artifact oracle 与 replay 读取 Issue #233 lifecycle adapter。
- CMake 使用既有 CMake runtime-parity/R0 组件；Make 使用 R3 Make action policy 与 R0 组件。
- 完整 `create_agent`、串行 tool call、请求 evidence、pre-model failure 分类和 cleanup 顺序通过本地 fake model gate 验证。
- 批次调度复用 behavioral pilot v2 已验证的单 asyncio loop 与三层 terminal taxonomy 模式；本阶段只实现纯状态转换合同，不复制 checkpoint capture/restore 或真实 pair 主循环。

## 终态与停止规则

- `endpoint_censored` 记录为 infrastructure attrition，不 replacement/backfill，并继续下一预注册 pair。
- `model_behavior_outcome` 与 verification failed/no-submit/graph-step-limit 都作为观察结果，继续另一 arm 与后续 pair。
- `mechanism_invalid`、identity drift、evidence write failure、cleanup failure 或 orphan 非零立即停止整个批次。
- 启动每个 pair 前检查累计 recorded tokens；达到或超过 2,940,000 后停止，禁止启动部分 pair。
- 每个 project block 两个 replicate 都可估计时才进入 project-level primary；否则只报告 attrition，不补跑。

## 当前授权

0 provider、0 credential read、0 model creation、0 reachability、0 Docker、0 checkpoint、0 pair、0 formal attempt、0 model token、0 正式 evidence write。未来真实执行必须新增 authorized amendment，绑定已合并的 release commit、一次 reachability 和同一个 12-pair schedule；本 candidate 不能直接执行。
