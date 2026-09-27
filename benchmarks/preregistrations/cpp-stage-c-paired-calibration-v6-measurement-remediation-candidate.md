# Stage C v6 测量链路修复候选预注册

日期：2026-09-27。追踪：[Issue #331](https://github.com/WWFXL/Forge-AutoCompiler/issues/331)。

## 目的

Stage C v5 已闭合 24 个 pair，但 Forge B 臂受到两类实现缺陷混杂：clean replay 在禁网容器中仍执行远程 `git fetch`；统一 evaluator 的 Stage C adapter 未覆盖 `command` oracle。v6 候选只评估这些测量链路修复，不重写或续跑 v5 identity。

## 第一阶段：离线定向重评

- 输入是 v5 中已经提交候选的 22 个 B 臂；两次没有候选的 civetweb attempt 不纳入重评。
- v5 候选、命令证据、产物、A 臂结果和模型输出全部只读，不调用 Provider，不生成替代候选。
- 每个重评从任务 exact commit 生成独立 `git archive`，校验既有 `source_snapshot_sha256` 后绑定到新 replay attempt。
- replay 使用冻结 image ID、空 workspace、`network=none` 和只读 `/repro/source.tar`。任何源码、候选或 image identity 漂移均在 Docker 执行前失败。
- oracle adapter 必须覆盖 `command`、`compile_and_run` 和 `service_probe`，并在批次开始前为 12 个冻结 task 全部构造和校验。
- 新 evidence 使用独立目录和 create-once identity；v5 manifest、报告、session 和 evidence 不得修改。

第一阶段只回答“已提交候选在修复后的测量链路下能否通过 S0-S5”。结果属于对 v5 的事后敏感性分析，不替代原始预注册结果，也不把 22 个 attempt 当作独立项目。

## 第二阶段判定

离线重评完成后再决定是否需要新的完整 paired calibration。若执行完整新实验，必须另行派生 authorized identity 和全新 A/B pair、attempt、thread、session 与 evidence；不得从本 candidate 直接开始正式执行。

## Token 与操作边界

- token 不设硬上限；`max_recorded_tokens`、阶段累计上限和 reachability token 上限均为 `null`。
- 每次模型请求必须记录 input、output 和 total token，并在 arm、batch 与最终报告中累计。token 累计值不得触发终止。
- 请求数、Agent 步骤数、工具调用数、命令数和墙钟上限继续生效。
- 第一阶段为零 Provider 重评，因此预期新增模型请求和 token 均为 0。

## 当前授权状态

本文件和配套 manifest 是未授权 candidate。当前只允许确定性生成、校验和显示重评计划；Provider 调用、凭据读取、Docker 执行、正式 attempt 注册和 evidence 写入均未授权。
